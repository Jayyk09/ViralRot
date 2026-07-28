"""Tests for collection management."""
import pytest
from unittest.mock import patch, MagicMock


class TestCollectionCreation:
    """Test collection CRUD operations."""

    @patch("services.collection_service.get_db_conn")
    def test_create_collection_returns_id(self, mock_conn):
        from services.collection_service import create_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = create_collection(user_id=1, collection_title="Test Collection")

        assert result == 42
        mock_cursor.execute.assert_called_once()

    @patch("services.collection_service.get_db_conn")
    def test_get_collection_returns_dict(self, mock_conn):
        from services.collection_service import get_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 1, "Test Collection", "2024-01-01")
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_collection(collection_id=1)

        assert result["id"] == 1
        assert result["collection_title"] == "Test Collection"

    @patch("services.collection_service.get_db_conn")
    def test_get_collection_returns_none_for_missing(self, mock_conn):
        from services.collection_service import get_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_collection(collection_id=999)

        assert result is None

    @patch("services.collection_service.get_db_conn")
    def test_get_user_collections_returns_list(self, mock_conn):
        from services.collection_service import get_user_collections

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 1, "Collection 1", "2024-01-01"),
            (2, 1, "Collection 2", "2024-01-02"),
        ]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_user_collections(user_id=1)

        assert len(result) == 2
        assert result[0]["collection_title"] == "Collection 1"

    @patch("services.collection_service.get_db_conn")
    def test_get_user_collections_uses_pagination(self, mock_conn):
        from services.collection_service import get_user_collections

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        get_user_collections(user_id=1, start=10, limit=5)

        # Verify OFFSET and LIMIT are in the query
        query = mock_cursor.execute.call_args[0][0]
        assert "OFFSET" in query or "offset" in query.lower()
        assert "LIMIT" in query or "limit" in query.lower()

    @patch("services.collection_service.get_db_conn")
    def test_find_last_collection_returns_most_recent(self, mock_conn):
        from services.collection_service import find_last_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5, 1, "Latest Collection", "2024-01-05")
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = find_last_collection(user_id=1)

        assert result["id"] == 5
        # Verify ORDER BY DESC is used
        query = mock_cursor.execute.call_args[0][0]
        assert "DESC" in query


class TestCollectionTitleGeneration:
    """Test AI-generated collection titles."""

    @patch("services.collection_service.genai")
    def test_generates_title_from_subtopics(self, mock_genai):
        from services.collection_service import generate_collection_title

        mock_response = MagicMock()
        mock_response.text = "Photosynthesis Masterclass"
        mock_genai.Client.return_value.models.generate_content.return_value = mock_response

        result = generate_collection_title(["Light Reactions", "Calvin Cycle", "Chloroplast"])

        assert "Photosynthesis" in result or len(result) > 0

    def test_handles_single_subtopic(self):
        from services.collection_service import generate_collection_title

        # With only one subtopic, it might just return that title
        result = generate_collection_title(["Single Topic"])

        assert result is not None
        assert len(result) > 0

    def test_handles_empty_list(self):
        from services.collection_service import generate_collection_title

        result = generate_collection_title([])

        # Should return some default or handle gracefully
        assert result is not None


class TestVideoCollectionAssociation:
    """Test video-collection associations."""

    @patch("services.repositories.video_repository.get_db_conn")
    @patch("services.video_service.get_storage_backend")
    def test_save_video_with_collection_id(self, mock_storage_factory, mock_conn):
        from services.video_service import VideoService
        from io import BytesIO

        # Mock storage backend
        mock_storage = MagicMock()
        mock_storage.generate_url.return_value = "https://storage.example.com/video.mp4"
        mock_storage_factory.return_value = mock_storage

        # Mock database
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (123,)
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        service = VideoService()
        fake_file = BytesIO(b"fake video content")

        result = service.save_video(
            user_id=1,
            editor_project_id="11111111-1111-4111-8111-111111111111",
            file_obj=fake_file,
            original_filename="test.mp4",
            title="Test Video",
            description="Test description",
            collection_id=5,
        )

        assert result["video_id"] == 123
        assert result["collection_id"] == 5

        # Verify collection_id is included in the INSERT query
        query = mock_cursor.execute.call_args[0][0]
        assert "collection_id" in query

    @patch("services.repositories.video_repository.get_db_conn")
    @patch("services.video_service.get_storage_backend")
    def test_get_collection_videos_returns_videos(self, mock_storage_factory, mock_conn):
        from services.video_service import VideoService

        # Mock storage backend
        mock_storage = MagicMock()
        mock_storage.generate_url.return_value = "https://storage.example.com/video.mp4"
        mock_storage_factory.return_value = mock_storage

        # Mock database
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 1, "s3/key1", "Video 1", "Subtopic 1/2", 5, "2024-01-01"),
            (2, 1, "s3/key2", "Video 2", "Subtopic 2/2", 5, "2024-01-02"),
        ]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        service = VideoService()
        result = service.get_collection_videos(collection_id=5)

        assert len(result) == 2
        # Videos should have presigned URLs
        assert all("presigned_url" in v for v in result)
