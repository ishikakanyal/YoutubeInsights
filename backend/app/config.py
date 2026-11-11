from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    webhdfs_url: str
    hdfs_user: str
    dashboard_path: str
    snapshot_file: str | None
    cache_seconds: float
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        )
        snapshot_file = os.getenv("ANALYTICS_SNAPSHOT_FILE", "").strip()
        return cls(
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
