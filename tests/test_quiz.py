"""Tests for quiz video generation pipeline."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend_pipeline.generate_quiz_video import (
    convert_quiz_to_transcript_format,
    load_quiz_modules,
    get_random_background_video,
)


class TestConvertQuizToTranscriptFormat:
    """Test quiz module to transcript conversion."""

    def test_adds_intro_line(self, sample_quiz_module):
        result = convert_quiz_to_transcript_format([sample_quiz_module])

        # First line should be intro
        first_line = result["transcripts"][0]
        assert "test your knowledge" in first_line["caption"].lower()
        assert first_line["speaker"] == "PETER"
        assert first_line["emotion"] == "excited"

    def test_adds_closing_line(self, sample_quiz_module):
        result = convert_quiz_to_transcript_format([sample_quiz_module])

        # Last line should be closing
        last_line = result["transcripts"][-1]
        assert "great job" in last_line["caption"].lower()
        assert last_line["speaker"] == "PETER"

    def test_creates_ask_and_reveal_for_each_question(self, sample_quiz_module):
        result = convert_quiz_to_transcript_format([sample_quiz_module])
        transcripts = result["transcripts"]

        # Should have entries containing "ask" and "reveal" text
        ask_texts = [t["caption"] for t in transcripts if "suck up" in t["caption"].lower() or "green" in t["caption"].lower()]
        reveal_texts = [t["caption"] for t in transcripts if "carbon dioxide" in t["caption"].lower() or "chlorophyll" in t["caption"].lower()]

        assert len(ask_texts) >= 1
        assert len(reveal_texts) >= 1

    def test_includes_options_for_multiple_choice(self, sample_quiz_module):
        result = convert_quiz_to_transcript_format([sample_quiz_module])
        transcripts = result["transcripts"]

        # Find options entries
        options_entries = [t for t in transcripts if t.get("is_options")]

        # Should have one options display per question
        assert len(options_entries) == 2  # 2 questions in sample_quiz_module

    def test_options_formatted_with_letters(self, sample_quiz_module):
        result = convert_quiz_to_transcript_format([sample_quiz_module])
        transcripts = result["transcripts"]

        options_entry = next(t for t in transcripts if t.get("is_options"))

        assert "A)" in options_entry["caption"]
        assert "B)" in options_entry["caption"]

    def test_handles_empty_modules_list(self):
        result = convert_quiz_to_transcript_format([])

        # Should only have closing line
        assert len(result["transcripts"]) == 1
        assert "great job" in result["transcripts"][0]["caption"].lower()


class TestLoadQuizModules:
    """Test loading quiz modules from JSON."""

    def test_loads_quiz_modules_format(self, temp_output_dir):
        json_file = temp_output_dir / "quiz.json"
        json_file.write_text('''
        {
            "quiz_modules": [
                {
                    "subtopic_title": "Topic 1",
                    "questions": []
                }
            ]
        }
        ''')

        result = load_quiz_modules(json_file)

        assert len(result) == 1
        assert result[0]["subtopic_title"] == "Topic 1"

    def test_raises_on_missing_quiz_modules(self, temp_output_dir):
        json_file = temp_output_dir / "quiz.json"
        json_file.write_text('{"invalid": "format"}')

        with pytest.raises(ValueError, match="must contain 'quiz_modules'"):
            load_quiz_modules(json_file)


class TestQuizVideoGeneration:
    """Test full quiz video generation pipeline."""

    @patch("backend_pipeline.generate_quiz_video.create_quiz_video_with_audio_and_captions")
    @patch("backend_pipeline.generate_quiz_video.concatenate_quiz_audio_segments")
    @patch("backend_pipeline.generate_quiz_video.generate_audio_from_quiz_transcript")
    @patch("backend_pipeline.generate_quiz_video.add_video")
    @patch("backend_pipeline.generate_quiz_video.find_last_collection")
    def test_generates_single_quiz_video(
        self,
        mock_find_collection,
        mock_add_video,
        mock_audio,
        mock_concat,
        mock_video,
        sample_quiz_modules,
        temp_output_dir,
    ):
        from backend_pipeline.generate_quiz_video import generate_quiz_video

        # Setup mocks
        mock_find_collection.return_value = {"id": 1}
        mock_add_video.return_value = 456
        mock_audio.return_value = [
            {"index": 0, "file": str(temp_output_dir / "test.mp3"), "is_pause": False}
        ]
        mock_concat.return_value = {
            "segments": [],
            "audio_file": str(temp_output_dir / "full.mp3"),
            "total_duration": 60
        }
        mock_video.return_value = str(temp_output_dir / "quiz.mp4")

        # Create mock background video
        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        result = generate_quiz_video(
            quiz_modules=sample_quiz_modules,
            background_video=bg_dir,
            output_dir=temp_output_dir / "output",
            audio_dir=temp_output_dir / "audio",
            user_id=1,
        )

        assert result["video_id"] == 456
        assert "Quiz:" in result["video_title"]

    @patch("backend_pipeline.generate_quiz_video.create_quiz_video_with_audio_and_captions")
    @patch("backend_pipeline.generate_quiz_video.concatenate_quiz_audio_segments")
    @patch("backend_pipeline.generate_quiz_video.generate_audio_from_quiz_transcript")
    @patch("backend_pipeline.generate_quiz_video.add_video")
    def test_uses_provided_collection_id(
        self,
        mock_add_video,
        mock_audio,
        mock_concat,
        mock_video,
        sample_quiz_modules,
        temp_output_dir,
    ):
        from backend_pipeline.generate_quiz_video import generate_quiz_video

        # Setup mocks
        mock_add_video.return_value = 789
        mock_audio.return_value = [
            {"index": 0, "file": str(temp_output_dir / "test.mp3"), "is_pause": False}
        ]
        mock_concat.return_value = {
            "segments": [],
            "audio_file": str(temp_output_dir / "full.mp3"),
            "total_duration": 60
        }
        mock_video.return_value = str(temp_output_dir / "quiz.mp4")

        # Create mock background video
        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        result = generate_quiz_video(
            quiz_modules=sample_quiz_modules,
            background_video=bg_dir,
            output_dir=temp_output_dir / "output",
            audio_dir=temp_output_dir / "audio",
            user_id=1,
            collection_id=99,  # Provide collection ID
            subtopic_count=5,  # Provide subtopic count
        )

        # Verify add_video was called with the provided collection_id
        call_kwargs = mock_add_video.call_args[1]
        assert call_kwargs["collection_id"] == 99

    def test_raises_on_empty_quiz_modules(self, temp_output_dir):
        from backend_pipeline.generate_quiz_video import generate_quiz_video

        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        with pytest.raises(ValueError, match="No quiz modules"):
            generate_quiz_video(
                quiz_modules=[],
                background_video=bg_dir,
                output_dir=temp_output_dir,
                audio_dir=temp_output_dir,
                user_id=1,
            )


class TestQuizDescriptionFormat:
    """Test quiz video description formatting."""

    @patch("backend_pipeline.generate_quiz_video.create_quiz_video_with_audio_and_captions")
    @patch("backend_pipeline.generate_quiz_video.concatenate_quiz_audio_segments")
    @patch("backend_pipeline.generate_quiz_video.generate_audio_from_quiz_transcript")
    @patch("backend_pipeline.generate_quiz_video.add_video")
    @patch("backend_pipeline.generate_quiz_video.find_last_collection")
    def test_description_includes_question_count(
        self,
        mock_find_collection,
        mock_add_video,
        mock_audio,
        mock_concat,
        mock_video,
        sample_quiz_modules,
        temp_output_dir,
    ):
        from backend_pipeline.generate_quiz_video import generate_quiz_video

        mock_find_collection.return_value = {"id": 1}
        mock_add_video.return_value = 1
        mock_audio.return_value = []
        mock_concat.return_value = {"segments": [], "audio_file": "", "total_duration": 0}
        mock_video.return_value = ""

        bg_dir = temp_output_dir / "backgrounds"
        bg_dir.mkdir()
        (bg_dir / "test.mp4").touch()

        generate_quiz_video(
            quiz_modules=sample_quiz_modules,
            background_video=bg_dir,
            output_dir=temp_output_dir / "output",
            audio_dir=temp_output_dir / "audio",
            user_id=1,
        )

        # Check the description passed to add_video
        call_kwargs = mock_add_video.call_args[1]
        assert "2 questions" in call_kwargs["description"]  # sample has 2 questions
