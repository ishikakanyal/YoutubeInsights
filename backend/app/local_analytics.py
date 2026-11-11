from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd


REGIONS = ("US", "CA", "GB", "DE", "FR", "IN", "JP", "KR", "MX", "RU")
CSV_COLUMNS = (
    "video_id",
    "trending_date",
    "title",
    "channel_title",
    "category_id",
    "publish_time",
    "views",
    "likes",
    "dislikes",
    "comment_count",
)


class LocalDatasetUnavailable(RuntimeError):
    """Local source data is missing or cannot produce a dashboard snapshot."""


def _read_region_csv(path: Path, region: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            path,
            usecols=list(CSV_COLUMNS),
            dtype=str,
            encoding="utf-8",
            encoding_errors="replace",
            keep_default_na=False,
            low_memory=False,
        )
    except (OSError, ValueError, pd.errors.ParserError, UnicodeError) as exc:
        raise LocalDatasetUnavailable(
            f"Could not read dataset file {path.name}: {exc}"
        ) from exc

    frame["region"] = region
    frame["category_id"] = pd.to_numeric(frame["category_id"], errors="coerce").astype(
        "Int64"
    )
    frame["trending_date"] = pd.to_datetime(
        frame["trending_date"], format="%y.%d.%m", errors="coerce"
    )
    frame["publish_date"] = pd.to_datetime(
        frame["publish_time"], errors="coerce", utc=True
    ).dt.strftime("%Y-%m-%d")
    frame["publish_date"] = frame["publish_date"].where(
        frame["publish_date"].notna(), None
    )

    for column, source in (
        ("views", "views"),
        ("likes", "likes"),
        ("dislikes", "dislikes"),
        ("comments", "comment_count"),
    ):
        frame[column] = (
            pd.to_numeric(frame[source], errors="coerce")
            .fillna(0)
            .astype("int64")
        )

    frame = frame.loc[
        frame["video_id"].notna()
        & frame["video_id"].str.strip().ne("")
        & frame["trending_date"].notna()
    ].copy()
    frame["trending_date"] = frame["trending_date"].dt.strftime("%Y-%m-%d")
    frame["category_id"] = frame["category_id"].map(
        lambda value: int(value) if pd.notna(value) else None
    )
    return frame[
        [
            "region",
            "video_id",
            "trending_date",
            "publish_date",
            "title",
            "channel_title",
            "category_id",
            "views",
            "likes",
            "dislikes",
            "comments",
        ]
    ]


def _read_categories(path: Path) -> dict[int, str]:
    try:
        with path.open(encoding="utf-8") as file:
            document = json.load(file)
        items = document["items"]
        return {
            int(item["id"]): item["snippet"].get("title")
            for item in items
            if item.get("id") is not None and item.get("snippet") is not None
        }
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise LocalDatasetUnavailable(
            f"Could not read category metadata {path.name}: {exc}"
        ) from exc


def _engagement_rate(views: int, likes: int, comments: int) -> float:
    if views <= 0:
        return 0.0
    rate = Decimal(likes + comments) * 100 / Decimal(views)
    return float(rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _group_metrics(
    frame: pd.DataFrame, keys: list[str]
) -> list[dict[str, Any]]:
    grouped = (
        frame.groupby(keys, dropna=False, sort=False)
        .agg(
            video_count=("video_id", "nunique"),
            views=("views", "sum"),
            likes=("likes", "sum"),
            comments=("comments", "sum"),
        )
        .reset_index()
    )
    rows: list[dict[str, Any]] = []
    for record in grouped.to_dict(orient="records"):
        row = {
            key: None if pd.isna(record[key]) else record[key]
            for key in keys
        }
        row.update(
            video_count=int(record["video_count"]),
            views=int(record["views"]),
            likes=int(record["likes"]),
            comments=int(record["comments"]),
        )
        row["engagement_rate"] = _engagement_rate(
            row["views"], row["likes"], row["comments"]
        )
        rows.append(row)
    return rows


def build_dashboard_payload(dataset_dir: Path) -> dict[str, Any]:
    dataset_dir = dataset_dir.expanduser()
    missing: list[str] = []
    csv_paths: dict[str, Path] = {}
    category_paths: dict[str, Path] = {}
    for region in REGIONS:
        csv_path = dataset_dir / f"{region}videos.csv"
        category_path = dataset_dir / f"{region}_category_id.json"
        if not csv_path.is_file():
            missing.append(csv_path.name)
        else:
            csv_paths[region] = csv_path
        if not category_path.is_file():
            missing.append(category_path.name)
        else:
            category_paths[region] = category_path
    if missing:
        raise LocalDatasetUnavailable(
            f"Local Kaggle dataset is missing {', '.join(missing)}. "
            f"Expected ten regional CSVs and ten category JSON files in {dataset_dir}."
        )

    frames = [_read_region_csv(csv_paths[region], region) for region in REGIONS]
    observations = pd.concat(frames, ignore_index=True)
    if observations.empty:
        raise LocalDatasetUnavailable(
            f"No valid observations were found in the CSV files under {dataset_dir}."
        )

    category_names: dict[tuple[str, int], str | None] = {}
    for region in REGIONS:
        category_names.update(
            {
                (region, category_id): name
                for category_id, name in _read_categories(
                    category_paths[region]
                ).items()
            }
        )
    observations["category"] = observations.apply(
        lambda row: category_names.get((row["region"], row["category_id"]))
        or (str(row["category_id"]) if row["category_id"] is not None else None),
        axis=1,
    )

    latest = (
        observations.sort_values("trending_date", ascending=False, kind="stable")
        .drop_duplicates(["region", "video_id"], keep="first")
        .copy()
    )
    countries = _group_metrics(latest, ["region"])
    observation_counts = observations.groupby("region")["video_id"].count().to_dict()
    for country in countries:
        country["observation_count"] = int(observation_counts[country["region"]])
    countries.sort(key=lambda row: row["region"])

    category_metrics = _group_metrics(
        latest, ["region", "category_id", "category"]
    )
    category_metrics.sort(
        key=lambda row: (
            row["region"],
            -row["views"],
            row["category"] or "",
        )
    )

    regional_channels = _group_metrics(latest, ["region", "channel_title"])
    regional_channels.sort(
        key=lambda row: (
            row["region"],
            -row["views"],
            row["channel_title"] or "",
        )
    )
    regional_channels = [
        row
        for region in sorted(REGIONS)
        for row in [
            metric
            for metric in regional_channels
            if metric["region"] == region
        ][:20]
    ]
    global_channels = _group_metrics(latest, ["channel_title"])
    global_channels.sort(
        key=lambda row: (-row["views"], row["channel_title"] or "")
    )
    global_channels = [
        {"region": "ALL", **row} for row in global_channels[:20]
    ]

    latest = latest.sort_values(
        ["region", "views", "video_id"],
        ascending=[True, False, True],
        kind="stable",
    )
    top_videos: list[dict[str, Any]] = []
    for region in sorted(REGIONS):
        for record in latest.loc[latest["region"].eq(region)].head(20).to_dict(
            orient="records"
        ):
            top_videos.append(
                {
                    "region": region,
                    "video_id": record["video_id"],
                    "title": record["title"],
                    "channel_title": record["channel_title"],
                    "category": record["category"],
                    "trending_date": record["trending_date"],
                    "publish_date": record["publish_date"],
                    "views": int(record["views"]),
                    "likes": int(record["likes"]),
                    "dislikes": int(record["dislikes"]),
                    "comments": int(record["comments"]),
                    "engagement_rate": _engagement_rate(
                        int(record["views"]),
                        int(record["likes"]),
                        int(record["comments"]),
                    ),
                }
            )

    trends_frame = (
        observations.groupby(["region", "trending_date"], dropna=False, sort=False)
        .agg(
            video_count=("video_id", "nunique"),
            views=("views", "sum"),
            likes=("likes", "sum"),
            comments=("comments", "sum"),
        )
        .reset_index()
    )
    trends: list[dict[str, Any]] = []
    for record in trends_frame.to_dict(orient="records"):
        views = int(record["views"])
        likes = int(record["likes"])
        comments = int(record["comments"])
        trends.append(
            {
                "region": record["region"],
                "trending_date": record["trending_date"],
                "video_count": int(record["video_count"]),
                "views": views,
                "likes": likes,
                "comments": comments,
                "engagement_rate": _engagement_rate(views, likes, comments),
            }
        )
    trends.sort(key=lambda row: (row["trending_date"], row["region"]))

    total_views = sum(row["views"] for row in countries)
    total_likes = sum(row["likes"] for row in countries)
    total_comments = sum(row["comments"] for row in countries)
    total_videos = sum(row["video_count"] for row in countries)
    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": str(dataset_dir.resolve()),
            "record_count": len(observations),
            "latest_video_count": total_videos,
            "regions": [row["region"] for row in countries],
            "metric_basis": "latest observation per region and video; trends use dated observations",
        },
        "overview": {
            "video_count": total_videos,
            "observation_count": len(observations),
            "views": total_views,
            "likes": total_likes,
            "comments": total_comments,
            "engagement_rate": _engagement_rate(
                total_views, total_likes, total_comments
            ),
        },
        "countries": countries,
        "categories": category_metrics,
        "channels": global_channels + regional_channels,
        "videos": top_videos,
        "trends": trends,
    }


class LocalAnalyticsRepository:
    def __init__(self, dataset_dir: Path, cache_seconds: float = 300.0) -> None:
        self.dataset_dir = dataset_dir
        self.cache_seconds = cache_seconds
        self._payload: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._lock = Lock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            if (
                self._payload is not None
                and now - self._cached_at < self.cache_seconds
            ):
                return self._payload
            self._payload = build_dashboard_payload(self.dataset_dir)
            self._cached_at = now
            return self._payload
