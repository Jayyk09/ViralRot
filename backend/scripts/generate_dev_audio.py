#!/usr/bin/env python3
"""
Dev fixture generator — runs MiniMax TTS once on the create2 mock transcript
and saves the result so the frontend can reload without burning API calls.

Run from the backend/ directory:
    python scripts/generate_dev_audio.py

Output:
    dev_fixtures/full_audio.mp3       — concatenated narration
    dev_fixtures/audio_result.json    — AudioResult-compatible fixture

Then enable the fixture in both development servers:
    backend/.env:        ENABLE_DEV_FIXTURES=true
    frontend/.env.local: NEXT_PUBLIC_DEV_FIXTURE=true
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend_pipeline.audio_generation.minimax_tts import (
    generate_audio_from_transcript,
    concatenate_audio_segments,
)

FIXTURES_DIR = Path(__file__).parent.parent / "dev_fixtures"
SEGMENTS_DIR = FIXTURES_DIR / "segments"
AUDIO_OUT    = FIXTURES_DIR / "full_audio.mp3"
RESULT_OUT   = FIXTURES_DIR / "audio_result.json"

# Mirrors MOCK_TRANSCRIPT in frontend/app/create2/page.tsx.
# UUIDs are generated once here and baked into the fixture — stable across reloads.
MOCK_LINES = [
    {"id": "a1b2c3d4-0001-0000-0000-000000000001", "speaker": "PETER",  "caption": "Hey Stewie, did you know that dolphins are basically just fish that went to college?",                          "emotion": "excited"},
    {"id": "a1b2c3d4-0001-0000-0000-000000000002", "speaker": "STEWIE", "caption": "That is factually incorrect on every conceivable level, you insufferable man-child.",                            "emotion": "angry"},
    {"id": "a1b2c3d4-0001-0000-0000-000000000003", "speaker": "PETER",  "caption": "No no, hear me out. They live in water, they swim around... fish.",                                             "emotion": "neutral"},
    {"id": "a1b2c3d4-0001-0000-0000-000000000004", "speaker": "STEWIE", "caption": "Dolphins are mammals. They breathe air, nurse their young, and have a neocortex. Unlike you.",                 "emotion": "angry"},
    {"id": "a1b2c3d4-0001-0000-0000-000000000005", "speaker": "PETER",  "caption": "Okay but have you ever seen a dolphin pay taxes? Exactly. Fish.",                                              "emotion": "excited"},
    {"id": "a1b2c3d4-0001-0000-0000-000000000006", "speaker": "STEWIE", "caption": "I genuinely cannot tell if you are joking or if this is just your brain working at full capacity.",            "emotion": "confused"},
    {"id": "a1b2c3d4-0001-0000-0000-000000000007", "speaker": "PETER",  "caption": "Full capacity, baby. Like a dolphin at college.",                                                              "emotion": "excited"},
]


def main():
    FIXTURES_DIR.mkdir(exist_ok=True)
    SEGMENTS_DIR.mkdir(exist_ok=True)

    print(f"\n🎙️  Generating dev fixture — {len(MOCK_LINES)} lines via MiniMax TTS")
    print(f"   Output → {FIXTURES_DIR}\n")

    segments = generate_audio_from_transcript(
        {"transcripts": MOCK_LINES},
        str(SEGMENTS_DIR),
    )
    result = concatenate_audio_segments(segments, str(AUDIO_OUT))

    # Build AudioResult-compatible JSON.
    # line_id comes from the input line; index is kept as a mapping bridge then
    # discarded on the frontend (LineTiming.index is not a stable identity).
    line_timings = []
    for timing, line in zip(result["timings"], MOCK_LINES):
        line_timings.append({
            "index":    timing["index"],
            "line_id":  line["id"],
            "start":    timing["start"],
            "end":      timing["end"],
            "duration": timing["duration"],
            "caption":  timing["caption"],
            "speaker":  timing["speaker"],
            "emotion":  timing["emotion"],
        })

    word_timestamps = []
    for wt in result["word_timestamps"]:
        idx = wt["line_index"]
        word_timestamps.append({
            "word":       wt["word"],
            "start":      wt["start"],
            "end":        wt["end"],
            "line_index": idx,
            "line_id":    MOCK_LINES[idx]["id"],
        })

    audio_result = {
        "audio_url":            "http://localhost:8000/dev/fixtures/full_audio.mp3",
        "background_video_url": "",
        "line_timings":         line_timings,
        "word_timestamps":      word_timestamps,
        "lines":                MOCK_LINES,
    }

    RESULT_OUT.write_text(json.dumps(audio_result, indent=2))

    total = result["total_duration"]
    print(f"\n✅ Fixture ready:")
    print(f"   Audio  → dev_fixtures/full_audio.mp3  ({total:.1f}s)")
    print(f"   JSON   → dev_fixtures/audio_result.json")
    print(f"\n💡 Enable fixture mode:")
    print(f"      backend/.env:        ENABLE_DEV_FIXTURES=true")
    print(f"      frontend/.env.local: NEXT_PUBLIC_DEV_FIXTURE=true")
    print(f"   then restart both dev servers and open /create2")


if __name__ == "__main__":
    main()
