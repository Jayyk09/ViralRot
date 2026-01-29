"""Tests for subtopic video generation pipeline."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend_pipeline.generate_subtopic_videos import (
    slugify,
    get_random_background_video,
    load_subtopics,
)


class TestSlugify:
    """Test slugify utility function."""

    def test_simple_text(self):
        assert slugify("Hello World") == "Hello_World"

    def test_special_characters(self):
        result = slugify("The Krebs Cycle!")
        assert "!" not in result
        assert "Krebs" in result

    def test_long_text_truncated(self):
        result = slugify("A" * 100)
        assert len(result) <= 64

    def test_empty_text_returns_default(self):
        assert slugify("") == "subtopic"

    def test_preserves_hyphens_and_underscores(self):
        assert slugify("my-topic_name") == "my-topic_name"

    def test_spaces_become_underscores(self):
        assert slugify("my topic name") == "my_topic_name"


class TestGetRandomBackgroundVideo:
    """Test background video selection."""

    def test_selects_mp4_from_directory(self, temp_output_dir):
        # Create fake video files
        (temp_output_dir / "video1.mp4").touch()
        (temp_output_dir / "video2.mp4").touch()
        (temp_output_dir / "not_a_video.txt").touch()

        result = get_random_background_video(temp_output_dir)

        assert result.suffix == ".mp4"
        assert result.parent == temp_output_dir

    def test_raises_on_missing_directory(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            get_random_background_video("/nonexistent/path/to/videos")

    def test_raises_on_empty_directory(self, temp_output_dir):
        with pytest.raises(FileNotFoundError, match="No background videos"):
            get_random_background_video(temp_output_dir)

    def test_raises_on_no_mp4_files(self, temp_output_dir):
        # Create non-mp4 files
        (temp_output_dir / "video.avi").touch()
        (temp_output_dir / "video.mov").touch()

        with pytest.raises(FileNotFoundError, match="No background videos"):
            get_random_background_video(temp_output_dir)


class TestLoadSubtopics:
    """Test loading subtopics from JSON."""

    def test_loads_subtopic_transcripts_format(self, temp_output_dir):
        json_file = temp_output_dir / "subtopics.json"
        json_file.write_text('''
        {
            "subtopic_transcripts": [
                {"subtopic_title": "Topic 1", "dialogue": []},
                {"subtopic_title": "Topic 2", "dialogue": []}
            ]
        }
        ''')

        result = load_subtopics(json_file)

        assert len(result) == 2
        assert result[0]["subtopic_title"] == "Topic 1"

    def test_loads_flat_transcripts_format(self, temp_output_dir):
        json_file = temp_output_dir / "subtopics.json"
        json_file.write_text('''
        {
            "transcripts": [
                {"caption": "Hello", "speaker": "PETER"}
            ]
        }
        ''')

        result = load_subtopics(json_file)

        assert len(result) == 1
        assert result[0]["subtopic_title"] == "subtopic_1"
        assert len(result[0]["dialogue"]) == 1

    def test_raises_on_invalid_format(self, temp_output_dir):
        json_file = temp_output_dir / "subtopics.json"
        json_file.write_text('{"invalid": "format"}')

        with pytest.raises(ValueError, match="must contain"):
            load_subtopics(json_file)


class TestSubtopicVideoGeneration:
    """Test full subtopic video generation pipeline."""

    @patch("backend_pipeline.generate_subtopic_videos.create_video_with_audio_and_captions")
    @patch("backend_pipeline.generate_subtopic_videos.concatenate_audio_segments")
    @patch("backend_pipeline.generate_subtopic_videos.generate_audio_from_transcript")
    @patch("backend_pipeline.generate_subtopic_videos.add_video")
    @patch("backend_pipeline.generate_subtopic_videos.create_collection")
    @patch("backend_pipeline.generate_subtopic_videos.generate_collection_title")
    def test_generates_video_for_each_subtopic(
        self,
        mock_title,
        mock_collection,
        mock_add_video,
        mock_audio,
        mock_concat,
        mock_video,
        sample_subtopics,
        temp_output_dir,
    ):
        from backend_pipeline.generate_subtopic_videos import generate_videos_from_subtopic_list

        # Setup mocks
        mock_title.return_value = "Test Collection"
        mock_collection.return_value = 1
        mock_add_video.return_value = 123
        mock_audio.return_value = [{"index": 0, "file": str(temp_output_dir / "test.mp3")}]
        mock_concat.return_value = {
            "audio_file": str(temp_output_dir / "full.mp3"),
            "timings": []
        }
        mock_video.return_value = str(temp_output_dir / "output.mp4")

        # Create mock background video
        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        results = generate_videos_from_subtopic_list(
            subtopics=sample_subtopics,
            background_video=bg_dir,
            output_dir=temp_output_dir / "output",
            audio_dir=temp_output_dir / "audio",
            user_id=1,
        )

        assert len(results) == 2
        assert all(r["video_id"] == 123 for r in results)
        assert all(r["collection_id"] == 1 for r in results)

    @patch("backend_pipeline.generate_subtopic_videos.create_video_with_audio_and_captions")
    @patch("backend_pipeline.generate_subtopic_videos.concatenate_audio_segments")
    @patch("backend_pipeline.generate_subtopic_videos.generate_audio_from_transcript")
    @patch("backend_pipeline.generate_subtopic_videos.add_video")
    @patch("backend_pipeline.generate_subtopic_videos.get_collection")
    def test_uses_existing_collection_when_provided(
        self,
        mock_get_collection,
        mock_add_video,
        mock_audio,
        mock_concat,
        mock_video,
        sample_subtopic_dialogue,
        temp_output_dir,
    ):
        from backend_pipeline.generate_subtopic_videos import generate_videos_from_subtopic_list

        # Setup mocks
        mock_get_collection.return_value = {"collection_title": "Existing Collection"}
        mock_add_video.return_value = 456
        mock_audio.return_value = [{"index": 0, "file": str(temp_output_dir / "test.mp3")}]
        mock_concat.return_value = {
            "audio_file": str(temp_output_dir / "full.mp3"),
            "timings": []
        }
        mock_video.return_value = str(temp_output_dir / "output.mp4")

        # Create mock background video
        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        results = generate_videos_from_subtopic_list(
            subtopics=[sample_subtopic_dialogue],
            background_video=bg_dir,
            output_dir=temp_output_dir / "output",
            audio_dir=temp_output_dir / "audio",
            user_id=1,
            collection_id=99,  # Provide existing collection
        )

        assert len(results) == 1
        assert results[0]["collection_id"] == 99
        mock_get_collection.assert_called_once_with(99)

    def test_raises_on_empty_subtopics(self, temp_output_dir):
        from backend_pipeline.generate_subtopic_videos import generate_videos_from_subtopic_list

        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        with pytest.raises(ValueError, match="No subtopics"):
            generate_videos_from_subtopic_list(
                subtopics=[],
                background_video=bg_dir,
                output_dir=temp_output_dir,
                audio_dir=temp_output_dir,
                user_id=1,
            )
