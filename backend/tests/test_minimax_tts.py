"""MiniMax TTS request contract tests."""

from unittest.mock import MagicMock, patch

from backend_pipeline.audio_generation.minimax_tts import generate_audio_from_dialouge


def test_tts_requests_lossless_wav_without_mp3_bitrate():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": {"audio": "776176", "status": 2},
        "extra_info": {"audio_length": 1000, "audio_format": "wav"},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }

    with patch(
        "backend_pipeline.audio_generation.minimax_tts.requests.post",
        return_value=response,
    ) as post:
        audio, duration, words = generate_audio_from_dialouge("Hello", "voice-id")

    payload = post.call_args.kwargs["json"]
    assert payload["audio_setting"] == {
        "sample_rate": 32000,
        "format": "wav",
        "channel": 1,
    }
    assert audio == b"wav"
    assert duration == 1.0
    assert words == []
