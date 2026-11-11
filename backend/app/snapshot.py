from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import quote

import requests

from app.config import Settings


class SnapshotUnavailable(RuntimeError):
    """The persisted Spark dashboard output cannot be read or is invalid."""


class SnapshotRepository:
    def __init__(self, settings: Settings, timeout_seconds: float = 10.0) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._lock = Lock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            if self._cached is not None and now - self._cached_at < self.settings.cache_seconds:
                return self._cached
            try:
                payload = self._read_local() if self.settings.snapshot_file else self._read_hdfs()
                self._validate(payload)
            except SnapshotUnavailable:
                raise
            except (OSError, ValueError, requests.RequestException, KeyError, TypeError) as exc:
                raise SnapshotUnavailable(
                    "Spark dashboard output is unavailable or invalid. Run the PySpark job "
                    "and verify HDFS WebHDFS connectivity and the configured output path."
                ) from exc
            self._cached = payload
            self._cached_at = now
            return payload

    def _read_local(self) -> dict[str, Any]:
        path = Path(self.settings.snapshot_file or "")
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _read_hdfs(self) -> dict[str, Any]:
        directory = self._webhdfs_url(self.settings.dashboard_path)
        response = requests.get(
            directory,
            params={"op": "LISTSTATUS", "user.name": self.settings.hdfs_user},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        entries = response.json()["FileStatuses"]["FileStatus"]
        part_files = sorted(
            entry["pathSuffix"]
            for entry in entries
            if entry["type"] == "FILE" and entry["pathSuffix"].startswith("part-")
        )
        if not part_files:
            raise SnapshotUnavailable(
                f"No Spark part files found in HDFS directory /{self.settings.dashboard_path}."
            )
        content: list[str] = []
        for name in part_files:
            response = requests.get(
                self._webhdfs_url(f"{self.settings.dashboard_path}/{name}"),
                params={"op": "OPEN", "user.name": self.settings.hdfs_user},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content.extend(line for line in response.text.splitlines() if line.strip())
        if len(content) != 1:
            raise SnapshotUnavailable(
                f"Expected one dashboard JSON record, found {len(content)} in Spark output."
            )
        return json.loads(content[0])

    def _webhdfs_url(self, path: str) -> str:
        encoded_path = quote("/" + path.strip("/"), safe="/")
        return f"{self.settings.webhdfs_url}{encoded_path}"

    @staticmethod
    def _validate(payload: Any) -> None:
        required = ("metadata", "overview", "countries", "categories", "channels", "videos", "trends")
        if not isinstance(payload, dict) or any(key not in payload for key in required):
            raise SnapshotUnavailable("Spark output is missing required dashboard fields.")
        if not isinstance(payload["metadata"], dict) or not isinstance(
            payload["metadata"].get("regions"), list
        ):
            raise SnapshotUnavailable("Spark output metadata is malformed.")
        for key in required[2:]:
            if not isinstance(payload[key], list):
                raise SnapshotUnavailable(f"Spark output field '{key}' must be an array.")

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None
            self._cached_at = 0.0
