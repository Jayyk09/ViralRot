"""Shared pytest fixtures for all tests."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import os


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setenv("XAI_MODEL", "grok-4.5")
    monkeypatch.setenv("SERPAPI_API_KEY", "test-serpapi-key")
    monkeypatch.setenv("IMAGE_CANDIDATE_SIGNING_KEY", "test-candidate-signing-key-32-bytes-min")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "test-group-id")
    monkeypatch.setenv("MINIMAX_PETER_VOICE", "test-peter-voice")
    monkeypatch.setenv("MINIMAX_STEWIE_VOICE", "test-stewie-voice")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", "/tmp/test-storage")


@pytest.fixture
def temp_output_dir():
    """Create temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_video_file(temp_output_dir):
    """Create a temporary fake video file."""
    video_path = temp_output_dir / "test_video.mp4"
    video_path.write_bytes(b"fake video content")
    return video_path


@pytest.fixture
def temp_audio_file(temp_output_dir):
    """Create a temporary fake audio file."""
    audio_path = temp_output_dir / "test_audio.wav"
    audio_path.write_bytes(b"fake audio content")
    return audio_path


@pytest.fixture
def mock_minimax_tts():
    """Mock MiniMax TTS API calls."""
    with patch("backend_pipeline.audio_generation.minimax_tts.requests.post") as mock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "audio": "666616b652d617564696f",  # hex-encoded "fake-audio"
                "status": 2
            },
            "extra_info": {
                "audio_length": 3000,  # 3 seconds in milliseconds
                "audio_format": "wav"
            },
            "base_resp": {
                "status_code": 0,
                "status_msg": "success"
            }
        }
        mock.return_value = mock_response
        yield mock


@pytest.fixture
def mock_db():
    """Mock database connections."""
    with patch("db.get_db_conn") as mock:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock.return_value = mock_conn
        yield mock_cursor


@pytest.fixture
def mock_r2():
    """Mock R2 client (legacy fixture - use mock_storage_backend for new code)."""
    with patch("storage.r2_backend.boto3") as mock:
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://r2.example.com/video.mp4"
        mock.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_storage_backend():
    """Mock storage backend for VideoService tests."""
    with patch("services.video_service.get_storage_backend") as mock_factory:
        mock_storage = MagicMock()
        mock_storage.upload.return_value = None
        mock_storage.generate_url.return_value = "https://storage.example.com/video.mp4"
        mock_storage.delete.return_value = None
        mock_storage.get_stats.return_value = {
            "backend": "Mock Storage",
            "total_files": 5,
            "total_size_human": "100.00 MB"
        }
        mock_factory.return_value = mock_storage
        yield mock_storage


@pytest.fixture
def mock_ffmpeg():
    """Mock FFmpeg subprocess calls."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout="10.5", stderr="")
        yield mock
