from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.snapshot import SnapshotRepository, SnapshotUnavailable


@pytest.fixture
def payload() -> dict:
    return {
        "metadata": {"regions": ["US"], "record_count": 1},
        "overview": {"video_count": 1},
        "countries": [{"region": "US"}],
        "categories": [],
        "channels": [],
        "videos": [],
        "trends": [],
    }


def make_settings(snapshot_file: str | None) -> Settings:
    return Settings(
        analytics_mode="hdfs",
        dataset_dir=Path("data/youtube-new"),
        local_cache_seconds=300,
        webhdfs_url="http://unused/webhdfs/v1",
        hdfs_user="hadoop",
        dashboard_path="/youtube/analytics/dashboard",
        snapshot_file=snapshot_file,
        cache_seconds=0,
        cors_origins=(),
    )


def test_analytics_mode_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANALYTICS_MODE", raising=False)

    settings = Settings.from_env()

    assert settings.analytics_mode == "local"
    assert settings.dataset_dir.name == "youtube-new"


def test_invalid_analytics_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYTICS_MODE", "spark")

    with pytest.raises(ValueError, match="ANALYTICS_MODE must be"):
        Settings.from_env()


def test_loads_actual_local_spark_snapshot(tmp_path: Path, payload: dict) -> None:
    path = tmp_path / "part-00000.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = SnapshotRepository(make_settings(str(path))).load()

    assert result == payload


def test_missing_snapshot_is_reported(tmp_path: Path) -> None:
    repository = SnapshotRepository(make_settings(str(tmp_path / "missing.json")))

    with pytest.raises(SnapshotUnavailable, match="Spark dashboard output is unavailable"):
        repository.load()


def test_invalid_snapshot_shape_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "part-00000.json"
    path.write_text('{"metadata": {}}', encoding="utf-8")

    with pytest.raises(SnapshotUnavailable, match="missing required dashboard fields"):
        SnapshotRepository(make_settings(str(path))).load()


def test_reads_spark_part_file_from_webhdfs(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    class Response:
        def __init__(self, value: dict | None = None, text: str = "") -> None:
            self.value = value
            self.text = text

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.value or {}

    responses = iter(
        [
            Response(
                {
                    "FileStatuses": {
                        "FileStatus": [
                            {"type": "FILE", "pathSuffix": "_SUCCESS"},
                            {"type": "FILE", "pathSuffix": "part-00000"},
                        ]
                    }
                }
            ),
            Response(text=json.dumps(payload)),
        ]
    )
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, *, params: dict, timeout: float) -> Response:
        calls.append((url, params))
        return next(responses)

    monkeypatch.setattr("app.snapshot.requests.get", fake_get)
    settings = make_settings(None)
    repository = SnapshotRepository(settings)

    assert repository.load() == payload
    assert calls[0][1]["op"] == "LISTSTATUS"
    assert calls[1][1]["op"] == "OPEN"
    assert calls[1][0].endswith("/youtube/analytics/dashboard/part-00000")
