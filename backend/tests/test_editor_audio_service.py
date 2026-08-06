"""Incremental editor narration service tests."""

from unittest.mock import MagicMock, patch
from uuid import UUID

from services.editor_audio_service import EditorAudioService


PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
LINE_ID = UUID("22222222-2222-4222-8222-222222222222")
SEGMENT_ID = UUID("33333333-3333-4333-8333-333333333333")


def test_generate_narration_reuses_ready_segments_and_activates_composition():
    service = EditorAudioService.__new__(EditorAudioService)
    service.repository = MagicMock()
    service.storage = MagicMock()
    line = {
        "id": LINE_ID,
        "caption": "Hello",
        "speaker": "PETER",
        "emotion": "neutral",
        "revision": 1,
    }
    service.repository.prepare_audio_generation.return_value = {
        "lines_to_generate": [line]
    }
    service.repository.get_composition_inputs.return_value = [
        {
            "line_id": LINE_ID,
            "segment_id": SEGMENT_ID,
            "storage_key": "segment.wav",
            "duration_ms": 1000,
            "word_timings": [{"word": "Hello", "start": 0.0, "end": 0.8}],
            "caption": "Hello",
            "speaker": "PETER",
            "emotion": "neutral",
        }
    ]
    service.storage.download.side_effect = lambda _key, path: open(path, "wb").write(b"wav")

    def fake_concatenate(_segments, output_file):
        open(output_file, "wb").write(b"combined")
        return {
            "total_duration": 1.0,
            "timings": [{
                "line_id": str(LINE_ID),
                "start": 0.0,
                "end": 1.0,
                "caption": "Hello",
                "speaker": "PETER",
                "emotion": "neutral",
            }],
            "word_timestamps": [],
        }

    with (
        patch(
            "services.editor_audio_service.generate_audio_from_dialouge",
            return_value=(b"audio", 1.0, []),
        ),
        patch(
            "services.editor_audio_service.concatenate_audio_segments",
            side_effect=fake_concatenate,
        ),
    ):
        result = service.generate_narration(PROJECT_ID, 1)

    assert result["duration_ms"] == 1000
    service.repository.prepare_audio_generation.assert_called_once_with(PROJECT_ID, 1)
    service.repository.complete_audio_segment.assert_called_once()
    service.repository.activate_composition.assert_called_once()
    activation = service.repository.activate_composition.call_args.args
    assert activation[0:2] == (PROJECT_ID, 1)
    assert activation[3].startswith(f"editor/1/{PROJECT_ID}/compositions/")
    assert activation[4] == 1000
    assert activation[5] == result["line_manifest"]
    # The service activates narration only; clip changes remain an explicit
    # visual-regeneration or manual-edit concern in the repository.
    assert service.storage.upload.call_count == 2
    segment_upload, composition_upload = service.storage.upload.call_args_list
    assert segment_upload.args[1].endswith(".wav")
    assert segment_upload.args[2] == {"content_type": "audio/wav"}
    assert composition_upload.args[1].endswith(".wav")
    assert composition_upload.args[2] == {"content_type": "audio/wav"}
