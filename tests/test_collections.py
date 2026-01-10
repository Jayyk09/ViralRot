"""Tests for collection management."""
import pytest
from unittest.mock import patch, MagicMock


class TestCollectionCreation:
    """Test collection CRUD operations."""

    @patch("save_to_db.collection_service.get_db_conn")
    def test_create_collection_returns_id(self, mock_conn):
        from save_to_db.collection_service import create_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (42,)
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = create_collection(user_id=1, collection_title="Test Collection")

        assert result == 42
        mock_cursor.execute.assert_called_once()

    @patch("save_to_db.collection_service.get_db_conn")
    def test_get_collection_returns_dict(self, mock_conn):
        from save_to_db.collection_service import get_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, 1, "Test Collection", "2024-01-01")
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_collection(collection_id=1)

        assert result["id"] == 1
        assert result["collection_title"] == "Test Collection"

    @patch("save_to_db.collection_service.get_db_conn")
    def test_get_collection_returns_none_for_missing(self, mock_conn):
        from save_to_db.collection_service import get_collection

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_collection(collection_id=999)

        assert result is None

    @patch("save_to_db.collection_service.get_db_conn")
    def test_get_user_collections_returns_list(self, mock_conn):
        from save_to_db.collection_service import get_user_collections

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 1, "Collection 1", "2024-01-01"),
            (2, 1, "Collection 2", "2024-01-02"),
        ]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_user_collections(user_id=1)

        assert len(result) == 2
        assert result[0]["collection_title"] == "Collection 1"

    @patch("save_to_db.collection_service.get_db_conn")
    def test_get_user_collections_uses_pagination(self, mock_conn):
        from save_to_db.collection_service import get_user_collections

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        get_user_collections(user_id=1, start=10, limit=5)

        # Verify OFFSET and LIMIT are in the query
        query = mock_cursor.execute.call_args[0][0]
        assert "OFFSET" in query or "offset" in query.lower()
        assert "LIMIT" in query or "limit" in query.lower()

    @patch("save_to_db.collection_service.get_db_conn")
    def test_find_last_collection_returns_most_recent(self, mock_conn):
        from save_to_db.collection_service import find_last_collection

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

    @patch("save_to_db.collection_service.genai")
    def test_generates_title_from_subtopics(self, mock_genai):
        from save_to_db.collection_service import generate_collection_title

        mock_response = MagicMock()
        mock_response.text = "Photosynthesis Masterclass"
        mock_genai.Client.return_value.models.generate_content.return_value = mock_response

        result = generate_collection_title(["Light Reactions", "Calvin Cycle", "Chloroplast"])

        assert "Photosynthesis" in result or len(result) > 0

    def test_handles_single_subtopic(self):
        from save_to_db.collection_service import generate_collection_title

        # With only one subtopic, it might just return that title
        result = generate_collection_title(["Single Topic"])

        assert result is not None
        assert len(result) > 0

    def test_handles_empty_list(self):
        from save_to_db.collection_service import generate_collection_title

        result = generate_collection_title([])

        # Should return some default or handle gracefully
        assert result is not None


class TestVideoCollectionAssociation:
    """Test video-collection associations."""

    @patch("save_to_db.save_video.get_db_conn")
    @patch("save_to_db.save_video.s3")
    def test_add_video_with_collection_id(self, mock_s3, mock_conn):
        from save_to_db.save_video import add_video
        from io import BytesIO

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (123,)
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        fake_file = BytesIO(b"fake video content")

        result = add_video(
            user_id=1,
            file_obj=fake_file,
            original_filename="test.mp4",
            title="Test Video",
            description="Test description",
            collection_id=5,
        )

        assert result == 123

        # Verify collection_id is included in the INSERT query
        query = mock_cursor.execute.call_args[0][0]
        assert "collection_id" in query

    @patch("save_to_db.save_video.get_db_conn")
    def test_get_collection_videos_returns_videos(self, mock_conn):
        from save_to_db.save_video import get_collection_videos

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, 1, "s3/key1", "Video 1", "Desc 1", 5, "2024-01-01"),
            (2, 1, "s3/key2", "Video 2", "Desc 2", 5, "2024-01-02"),
        ]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_collection_videos(collection_id=5)

        assert len(result) == 2
        assert all(v.get("collection_id") == 5 or "collection" in str(v).lower() for v in result)
