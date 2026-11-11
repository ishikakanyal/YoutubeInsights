from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    analytics_mode: str
    dataset_dir: Path
    local_cache_seconds: float
    webhdfs_url: str
    hdfs_user: str
    dashboard_path: str
    snapshot_file: str | None
    cache_seconds: float
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        analytics_mode = os.getenv("ANALYTICS_MODE", "local").strip().lower()
        if analytics_mode not in {"local", "hdfs"}:
            raise ValueError("ANALYTICS_MODE must be either 'local' or 'hdfs'.")
        origins = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        snapshot_file = os.getenv("ANALYTICS_SNAPSHOT_FILE", "").strip()
        default_dataset_dir = Path(__file__).resolve().parents[2] / "data" / "youtube-new"
        return cls(
            analytics_mode=analytics_mode,
            dataset_dir=Path(
                os.getenv("ANALYTICS_DATASET_DIR", str(default_dataset_dir))
            ).expanduser(),
            local_cache_seconds=max(
                0.0, float(os.getenv("LOCAL_ANALYTICS_CACHE_SECONDS", "300"))
            ),
            webhdfs_url=os.getenv(
                "HDFS_WEBHDFS_URL", "http://localhost:9870/webhdfs/v1"
            ).rstrip("/"),
            hdfs_user=os.getenv("HDFS_USER", "hadoop"),
            dashboard_path=os.getenv(
                "HDFS_DASHBOARD_PATH", "/youtube/analytics/dashboard"
            ).strip("/"),
            snapshot_file=snapshot_file or None,
            cache_seconds=max(0.0, float(os.getenv("SNAPSHOT_CACHE_SECONDS", "15"))),
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        )
