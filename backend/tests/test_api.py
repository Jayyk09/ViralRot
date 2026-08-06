"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_returns_pipeline_info(self, client):
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "pipeline" in data
        assert "frontend" in data["pipeline"]
        assert "backend" in data["pipeline"]

    def test_health_check_returns_healthy(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestVideoEndpoints:
    """Test video listing endpoints."""

    @patch("main.VideoService")
    def test_list_user_videos_includes_project_exports(self, service_cls, client):
        service = service_cls.return_value
        service.get_user_videos.return_value = [
            {
                "id": 7,
                "title": "Project export",
                "description": "Generated from persistent editor project",
                "presigned_url": "https://example.test/export.mp4",
                "storage_key": "1/private.mp4",
            }
        ]
        service.get_video_count.return_value = 1

        response = client.get("/videos")

        assert response.status_code == 200
        data = response.json()
        assert data["total_videos"] == 1
        assert "storage_key" not in data["videos"][0]

    @patch("main.VideoService")
    def test_list_videos_uses_video_pagination(self, service_cls, client):
        service = service_cls.return_value
        service.get_user_videos.return_value = []
        service.get_video_count.return_value = 12

        response = client.get("/videos?offset=5&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 5
        assert data["limit"] == 2
        assert data["total_videos"] == 12
        service.get_user_videos.assert_called_once_with(1, 5, 2)
