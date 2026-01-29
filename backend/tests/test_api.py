"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


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


class TestVideoGenerationEndpoint:
    """Test /generate-video endpoint."""

    def test_rejects_missing_content_for_text(self, client):
        response = client.post(
            "/generate-video",
            data={"input_type": "text", "user_id": "1"}
        )

        assert response.status_code == 400

    def test_rejects_invalid_input_type(self, client):
        response = client.post(
            "/generate-video",
            data={"input_type": "invalid", "user_id": "1", "content": "test"}
        )

        assert response.status_code == 400

    @patch("main._validate_background_video")
    @patch("main._run_blocking")
    def test_auto_detects_youtube_url(self, mock_run, mock_validate, client):
        mock_run.side_effect = [
            [],  # extract_transcripts returns empty
        ]

        response = client.post(
            "/generate-video",
            data={
                "input_type": "auto",
                "user_id": "1",
                "content": "https://youtube.com/watch?v=abc123"
            }
        )

        # Should detect as YouTube and attempt processing
        # Will fail because extract_transcripts returns empty, but validates detection
        assert mock_run.called

    @patch("main._validate_background_video")
    @patch("main._run_blocking")
    def test_auto_detects_text_content(self, mock_run, mock_validate, client):
        mock_run.return_value = []  # extract_transcripts returns empty

        response = client.post(
            "/generate-video",
            data={
                "input_type": "auto",
                "user_id": "1",
                "content": "This is plain text content about photosynthesis."
            }
        )

        # Should detect as text
        assert mock_run.called


class TestCollectionEndpoints:
    """Test collection management endpoints."""

    @patch("main._run_blocking")
    def test_list_collections_returns_list(self, mock_run, client):
        mock_run.return_value = [
            {"id": 1, "collection_title": "Test Collection 1"},
            {"id": 2, "collection_title": "Test Collection 2"},
        ]

        response = client.get("/collections")

        assert response.status_code == 200
        data = response.json()
        assert "collections" in data
        assert len(data["collections"]) == 2

    @patch("main._run_blocking")
    def test_list_collections_with_pagination(self, mock_run, client):
        mock_run.return_value = [
            {"id": 3, "collection_title": "Collection 3"},
        ]

        response = client.get("/collections?start=2&limit=1")

        assert response.status_code == 200
        mock_run.assert_called()

    @patch("main._run_blocking")
    def test_get_collection_details(self, mock_run, client):
        mock_run.side_effect = [
            {"id": 1, "user_id": 1, "collection_title": "Test Collection"},  # get_collection
            [{"id": 1, "video_title": "Video 1"}]  # get_collection_videos
        ]

        response = client.get("/collections/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert "videos" in data

    @patch("main._run_blocking")
    def test_get_collection_not_found(self, mock_run, client):
        mock_run.return_value = None  # Collection not found

        response = client.get("/collections/999")

        assert response.status_code == 404

    @patch("main._run_blocking")
    def test_get_collection_forbidden_for_other_user(self, mock_run, client):
        mock_run.return_value = {"id": 1, "user_id": 999, "collection_title": "Other User's Collection"}

        response = client.get("/collections/1")

        assert response.status_code == 403


class TestVideoEndpoints:
    """Test video listing endpoints."""

    @patch("main._run_blocking")
    def test_list_user_videos(self, mock_run, client):
        # Mock get_user_collections and get_collection_videos
        mock_run.side_effect = [
            [{"id": 1, "collection_title": "Collection 1"}],  # get_user_collections (paginated)
            [{"id": 1, "collection_title": "Collection 1"}],  # get_user_collections (for total)
            [{"id": 1, "title": "Video 1", "collection_id": 1}],  # get_collection_videos
        ]

        response = client.get("/videos")

        assert response.status_code == 200
        data = response.json()
        assert "videos" in data
        assert "total_collections" in data

    @patch("main._run_blocking")
    def test_list_videos_with_collection_pagination(self, mock_run, client):
        mock_run.side_effect = [
            [],  # get_user_collections returns empty for offset
            [{"id": 1}],  # total collections
        ]

        response = client.get("/videos?collection_offset=5&collection_limit=2")

        assert response.status_code == 200
        data = response.json()
        assert data["collection_offset"] == 5
        assert data["collection_limit"] == 2


class TestAccountEndpoints:
    """Test user account endpoints."""

    @patch("main._run_blocking")
    def test_register_account_success(self, mock_run, client):
        mock_run.return_value = {"id": 1, "email": "test@example.com"}

        response = client.post(
            "/accounts",
            json={"email": "test@example.com", "password": "password123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == "test@example.com"

    @patch("main._run_blocking")
    def test_register_account_duplicate_email(self, mock_run, client):
        mock_run.return_value = None  # Email already exists

        response = client.post(
            "/accounts",
            json={"email": "existing@example.com", "password": "password123"}
        )

        assert response.status_code == 400

    @patch("main._run_blocking")
    def test_login_success(self, mock_run, client):
        mock_run.return_value = {"id": 1, "email": "test@example.com"}

        response = client.post(
            "/accounts/login",
            json={"email": "test@example.com", "password": "password123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Login successful"

    @patch("main._run_blocking")
    def test_login_invalid_credentials(self, mock_run, client):
        mock_run.return_value = None  # Auth failed

        response = client.post(
            "/accounts/login",
            json={"email": "test@example.com", "password": "wrong"}
        )

        assert response.status_code == 401

    @patch("main._run_blocking")
    def test_get_account_by_id(self, mock_run, client):
        mock_run.return_value = {"id": 1, "email": "test@example.com"}

        response = client.get("/accounts/1")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"

    @patch("main._run_blocking")
    def test_get_account_not_found(self, mock_run, client):
        mock_run.return_value = None

        response = client.get("/accounts/999")

        assert response.status_code == 404

    @patch("main._run_blocking")
    def test_list_accounts(self, mock_run, client):
        mock_run.return_value = [
            {"id": 1, "email": "alice@example.com"},
            {"id": 2, "email": "bob@example.com"},
        ]

        response = client.get("/accounts")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["users"]) == 2
