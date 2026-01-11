"""Shared pytest fixtures for all tests."""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import os


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-elevenlabs-key")
    monkeypatch.setenv("Peter_voiceId", "test-peter-voice")
    monkeypatch.setenv("Stewie_voiceId", "test-stewie-voice")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def sample_subtopic_dialogue():
    """Sample subtopic dialogue for testing."""
    return {
        "subtopic_title": "Photosynthesis Basics",
        "dialogue": [
            {"caption": "Hey Stewie, ever wonder how plants eat?", "speaker": "PETER", "emotion": "excited"},
            {"caption": "Plants dont eat, Peter. They photosynthesize.", "speaker": "STEWIE", "emotion": "neutral"},
            {"caption": "Photo-what now?", "speaker": "PETER", "emotion": "confused"},
            {"caption": "They convert sunlight into energy. Its quite brilliant.", "speaker": "STEWIE", "emotion": "excited"},
        ]
    }


@pytest.fixture
def sample_subtopics(sample_subtopic_dialogue):
    """Sample list of subtopics for testing."""
    return [
        sample_subtopic_dialogue,
        {
            "subtopic_title": "Light Reactions",
            "dialogue": [
                {"caption": "So what happens in the light?", "speaker": "PETER", "emotion": "neutral"},
                {"caption": "Chlorophyll absorbs light energy.", "speaker": "STEWIE", "emotion": "teaching"},
            ]
        }
    ]


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
    audio_path = temp_output_dir / "test_audio.mp3"
    audio_path.write_bytes(b"fake audio content")
    return audio_path


@pytest.fixture
def mock_elevenlabs():
    """Mock ElevenLabs API calls."""
    with patch("backend_pipeline.audio_generation.elevenLabs.client") as mock:
        mock.text_to_speech.convert.return_value = iter([b"fake-audio-data"])
        yield mock


@pytest.fixture
def mock_gemini():
    """Mock Gemini API calls."""
    with patch("frontend_pipeline.script_generation.transcripts.genai") as mock:
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
def mock_s3():
    """Mock S3 client."""
    with patch("save_to_db.save_video.s3") as mock:
        mock.generate_presigned_url.return_value = "https://s3.example.com/video.mp4"
        yield mock


@pytest.fixture
def mock_ffmpeg():
    """Mock FFmpeg subprocess calls."""
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout="10.5", stderr="")
        yield mock
