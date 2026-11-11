from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.snapshot import SnapshotUnavailable


class StaticRepository:
    def __init__(self, value: dict | Exception) -> None:
        self.value = value

    def load(self) -> dict:
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def sample_payload() -> dict:
    country = {
        "region": "US",
        "video_count": 1,
        "observation_count": 2,
        "views": 100,
        "likes": 10,
        "comments": 5,
        "engagement_rate": 15.0,
    }
    return {
        "metadata": {"regions": ["US"], "record_count": 2},
        "overview": {
            "video_count": 1,
            "observation_count": 2,
            "views": 100,
            "likes": 10,
            "comments": 5,
            "engagement_rate": 15.0,
        },
        "countries": [country],
        "categories": [{"region": "US", "category": "Music"}],
        "channels": [{"region": "US", "channel_title": "Example"}],
        "videos": [{"region": "US", "video_id": "video-1"}],
        "trends": [{"region": "US", "trending_date": "2017-11-14"}],
    }


def test_dashboard_filters_by_region() -> None:
    with TestClient(app) as client:
        app.state.snapshots = StaticRepository(sample_payload())

        response = client.get("/api/dashboard?region=us")

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["selected_region"] == "US"
    assert data["overview"]["observation_count"] == 2
    assert all(row["region"] == "US" for row in data["trends"])


def test_dashboard_reports_missing_distributed_output() -> None:
    with TestClient(app) as client:
        app.state.snapshots = StaticRepository(SnapshotUnavailable("Run the Spark job."))

        response = client.get("/api/dashboard")

    assert response.status_code == 503
    assert response.json()["detail"] == "Run the Spark job."


def test_unknown_region_is_not_returned_as_empty_success() -> None:
    with TestClient(app) as client:
        app.state.snapshots = StaticRepository(sample_payload())

        response = client.get("/api/dashboard?region=GB")

    assert response.status_code == 404
