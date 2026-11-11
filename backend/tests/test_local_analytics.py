from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.local_analytics import (
    LocalAnalyticsRepository,
    LocalDatasetUnavailable,
    REGIONS,
    _engagement_rate,
    build_dashboard_payload,
)
from app.main import app


SPARK_SCHEMA = {
    "metadata": {
        "generated_at",
        "source",
        "record_count",
        "latest_video_count",
        "regions",
        "metric_basis",
    },
    "overview": {
        "video_count",
        "observation_count",
        "views",
        "likes",
        "comments",
        "engagement_rate",
    },
    "countries": {
        "region",
        "video_count",
        "views",
        "likes",
        "comments",
        "engagement_rate",
        "observation_count",
    },
    "categories": {
        "region",
        "category_id",
        "category",
        "video_count",
        "views",
        "likes",
        "comments",
        "engagement_rate",
    },
    "channels": {
        "region",
        "channel_title",
        "video_count",
        "views",
        "likes",
        "comments",
        "engagement_rate",
    },
    "videos": {
        "region",
        "video_id",
        "title",
        "channel_title",
        "category",
        "trending_date",
        "publish_date",
        "views",
        "likes",
        "dislikes",
        "comments",
        "engagement_rate",
    },
    "trends": {
        "region",
        "trending_date",
        "video_count",
        "views",
        "likes",
        "comments",
        "engagement_rate",
    },
}

CSV_HEADER = [
    "video_id",
    "trending_date",
    "title",
    "channel_title",
    "category_id",
    "publish_time",
    "tags",
    "views",
    "likes",
    "dislikes",
    "comment_count",
    "thumbnail_link",
    "comments_disabled",
    "ratings_disabled",
    "video_error_or_removed",
    "description",
]


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    rows_by_region = {
        "US": [
            ("video-1", "17.14.11", "Old title", "Channel A", "1", "2017-11-13T10:00:00Z", "100", "10", "1", "2"),
            ("video-1", "17.15.11", "Latest title", "Channel A", "1", "2017-11-14T10:00:00Z", "200", "20", "2", "4"),
            ("video-2", "17.15.11", "Zero views", "Channel B", "99", "2017-11-14T10:00:00Z", "0", "3", "0", "0"),
        ]
    }
    for region in REGIONS:
        rows = rows_by_region.get(
            region,
            [
                (
                    f"{region}-video",
                    "17.15.11",
                    f"{region} title",
                    f"{region} Channel",
                    "1",
                    "2017-11-14T10:00:00Z",
                    "0",
                    "0",
                    "0",
                    "0",
                )
            ],
        )
        with (tmp_path / f"{region}videos.csv").open(
            "w", encoding="utf-8", newline=""
        ) as file:
            writer = csv.writer(file)
            writer.writerow(CSV_HEADER)
            for record in rows:
                (
                    video_id,
                    trending_date,
                    title,
                    channel_title,
                    category_id,
                    publish_time,
                    views,
                    likes,
                    dislikes,
                    comments,
                ) = record
                writer.writerow(
                    [
                        video_id,
                        trending_date,
                        title,
                        channel_title,
                        category_id,
                        publish_time,
                        "",
                        views,
                        likes,
                        dislikes,
                        comments,
                        "",
                        "False",
                        "False",
                        "False",
                        "",
                    ]
                )
        (tmp_path / f"{region}_category_id.json").write_text(
            json.dumps(
                {
                    "items": [
                        {"id": "1", "snippet": {"title": "Music"}},
                    ]
                }
            ),
            encoding="utf-8",
        )
    return tmp_path


def test_payload_matches_spark_dashboard_schema(dataset_dir: Path) -> None:
    payload = build_dashboard_payload(dataset_dir)

    assert set(payload) == set(SPARK_SCHEMA)
    for key, fields in SPARK_SCHEMA.items():
        if key in {"metadata", "overview"}:
            assert set(payload[key]) == fields
        else:
            assert payload[key]
            assert all(set(row) == fields for row in payload[key])


def test_latest_observations_and_engagement_calculations(dataset_dir: Path) -> None:
    payload = build_dashboard_payload(dataset_dir)

    assert payload["metadata"]["record_count"] == 12
    assert payload["metadata"]["latest_video_count"] == 11
    assert payload["overview"] == {
        "video_count": 11,
        "observation_count": 12,
        "views": 200,
        "likes": 23,
        "comments": 4,
        "engagement_rate": 13.5,
    }

    us_country = next(row for row in payload["countries"] if row["region"] == "US")
    assert us_country == {
        "region": "US",
        "video_count": 2,
        "views": 200,
        "likes": 23,
        "comments": 4,
        "engagement_rate": 13.5,
        "observation_count": 3,
    }

    latest_video = next(
        row for row in payload["videos"] if row["video_id"] == "video-1"
    )
    assert latest_video["title"] == "Latest title"
    assert latest_video["trending_date"] == "2017-11-15"
    assert latest_video["engagement_rate"] == 12.0
    zero_view_video = next(
        row for row in payload["videos"] if row["video_id"] == "video-2"
    )
    assert zero_view_video["engagement_rate"] == 0.0
    assert zero_view_video["category"] == "99"

    old_trend = next(
        row
        for row in payload["trends"]
        if row["region"] == "US" and row["trending_date"] == "2017-11-14"
    )
    assert old_trend["views"] == 100
    assert old_trend["engagement_rate"] == 12.0


def test_local_analytics_cache_avoids_reprocessing(
    dataset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.local_analytics as module

    original = module.build_dashboard_payload
    calls = 0

    def count_builds(path: Path) -> dict:
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(module, "build_dashboard_payload", count_builds)
    repository = LocalAnalyticsRepository(dataset_dir, cache_seconds=60)

    first = repository.load()
    second = repository.load()

    assert first is second
    assert calls == 1


def test_missing_local_dataset_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(LocalDatasetUnavailable, match="Local Kaggle dataset is missing"):
        build_dashboard_payload(tmp_path)


def test_engagement_rate_rounds_half_up_like_spark() -> None:
    assert _engagement_rate(2_000_000, 1, 0) == 0.0001
    assert _engagement_rate(0, 100, 50) == 0.0


def test_local_api_serves_pandas_snapshot(
    dataset_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANALYTICS_MODE", "local")
    monkeypatch.setenv("ANALYTICS_DATASET_DIR", str(dataset_dir))
    with TestClient(app) as client:
        health = client.get("/api/health")
        response = client.get("/api/dashboard?region=US")

    assert health.json()["analytics_mode"] == "local"
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["analytics_mode"] == "local"
    assert data["overview"]["views"] == 200


def test_local_api_reports_missing_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANALYTICS_MODE", "local")
    monkeypatch.setenv("ANALYTICS_DATASET_DIR", str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/dashboard")

    assert response.status_code == 503
    assert "Local Kaggle dataset is missing" in response.json()["detail"]
