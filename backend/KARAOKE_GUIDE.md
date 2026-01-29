# Karaoke Caption Mode Guide

This guide explains the karaoke-style caption system that provides word-by-word highlighting during video playback.

## Overview

The video generation system supports two caption modes:

| Mode | Description | Default |
|------|-------------|---------|
| **Karaoke** | Words highlight yellow one-by-one as spoken | YES |
| **Box** | Traditional white text in semi-transparent black boxes | NO |

## Visual Comparison

### Karaoke Mode (Default)
```
Hey Stewie, you ever wonder about photosynthesis?
^^^                                              <- Yellow (being spoken)
    ^^^^^^                                       <- White (not yet spoken)
```
- Clean, transparent background
- Words illuminate progressively as audio plays
- Modern, engaging appearance

### Box Caption Mode
```
┌─────────────────────────────────────────────────┐
│ Hey Stewie, you ever wonder about photosynthesis? │
└─────────────────────────────────────────────────┘
```
- Semi-transparent black background box
- Entire caption visible at once
- Traditional subtitle appearance

## API Usage

### Default Behavior (Karaoke ON)

When calling the video generation endpoint without specifying caption mode, karaoke captions are used:

```bash
curl -X POST http://localhost:8000/jobs/generate-video \
  -F "transcript_id=abc123" \
  -F "user_id=1"
```

### Explicitly Enable Karaoke

```bash
curl -X POST http://localhost:8000/jobs/generate-video \
  -F "transcript_id=abc123" \
  -F "user_id=1" \
  -F "karaoke_captions=true"
```

### Disable Karaoke (Use Box Captions)

```bash
curl -X POST http://localhost:8000/jobs/generate-video \
  -F "transcript_id=abc123" \
  -F "user_id=1" \
  -F "karaoke_captions=false"
```

### Response Format

The job creation response includes the caption mode setting:

```json
{
  "job_id": "abc123xyz",
  "job_type": "video_generation",
  "dialogue_title": "Peter Explains Photosynthesis",
  "karaoke_captions": true,
  "message": "Video generation started. Connect to WebSocket for progress.",
  "websocket_url": "/ws/progress/abc123xyz",
  "status_url": "/jobs/abc123xyz/progress"
}
```

## CLI Usage

### Test with Karaoke (Default)

```bash
python test_image_overlay.py --config test_configs/my_config.json --karaoke
```

### Test with Box Captions

```bash
python test_image_overlay.py --config test_configs/my_config.json
```

### Full Pipeline with Karaoke

```bash
python cli.py --source "Your content here" --source-type text --user-id 1
```

The CLI uses karaoke mode by default. To use box captions, modify the `cli.py` call to `generate_video_from_dialogue` with `karaoke_captions=False`.

## Technical Implementation

### ASS Subtitle Format

Karaoke captions use the **ASS (Advanced SubStation Alpha)** subtitle format, which supports:
- Per-character timing with `\k` tags
- Color transitions (white -> yellow)
- Transparent backgrounds
- Custom fonts and positioning

### Generated ASS Example

```ass
[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, ...
Style: Default,Arial,72,&H00FFFFFF,&H0000FFFF,...

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.50,Default,,0,0,50,,{\k35}Hey {\k45}Stewie, {\k30}you {\k40}ever...
```

### Word Timing Algorithm

Words are timed proportionally based on their length:
1. Calculate total character count in caption
2. Distribute duration across words based on character count
3. Add `\k` tags with centisecond durations

Example for "Hey Stewie" over 1 second:
- "Hey" (3 chars) = 30% = 300ms = `\k30`
- "Stewie" (6 chars) = 60% = 600ms = `\k60`
- Comma pause = 10% = 100ms

## File Structure

```
backend_pipeline/
├── video_assembly/
│   ├── ass_generator.py      # ASS subtitle generation
│   └── ffMpeg.py             # Video assembly with caption_mode param
└── generate_video.py         # Main entry point with karaoke_captions param
```

### Key Functions

**`ass_generator.py`**:
- `create_karaoke_subtitle_file(dialogue_lines, audio_durations, output_path)` - Generates ASS file
- `calculate_word_timings(text, duration)` - Computes per-word durations
- `format_ass_time(seconds)` - Converts to ASS time format

**`ffMpeg.py`**:
- `create_video_with_overlay(..., caption_mode="karaoke"|"box")` - Assembles final video

**`generate_video.py`**:
- `generate_video_from_dialogue(..., karaoke_captions=True)` - Main orchestration

## Troubleshooting

### Issue: Karaoke timing feels off

**Cause**: Words are timed proportionally by character count, not phonetic duration.

**Solution**: For better timing, consider:
1. Keep captions short (under 15 words)
2. Use natural speech patterns in dialogue
3. Avoid very long words mixed with short words

### Issue: Special characters not displaying

**Cause**: ASS format requires escaping certain characters.

**Solution**: The generator automatically escapes:
- `{` and `}` (ASS control characters)
- `\n` (newlines converted to `\N`)

### Issue: Captions cut off or overlap

**Cause**: Very long captions may exceed safe display area.

**Solution**: 
1. Keep captions under 20 words (enforced by dialogue generation)
2. The system wraps long lines automatically

### Issue: Yellow color not visible

**Cause**: Background video may have yellow/bright areas.

**Solution**: The karaoke style uses:
- Yellow: `&H00FFFF` (BGR format)
- With outline: 2px black border for contrast

## Configuration Options

### Caption Style (in `ass_generator.py`)

```python
KARAOKE_STYLE = {
    "font": "Arial",
    "size": 72,
    "primary_color": "&H00FFFFFF",    # White (not yet spoken)
    "secondary_color": "&H0000FFFF",  # Yellow (being spoken)
    "outline_color": "&H00000000",    # Black outline
    "outline_width": 2,
    "alignment": 2,  # Bottom center
    "margin_v": 50,  # Vertical margin from bottom
}
```

### Adjusting Colors

Colors in ASS are BGR format (not RGB):
- White: `&H00FFFFFF`
- Yellow: `&H0000FFFF`
- Red: `&H000000FF`
- Blue: `&H00FF0000`

## Performance Considerations

- ASS files are generated per-video (not cached)
- File size is minimal (~1-5KB per video)
- FFmpeg's `libass` filter handles rendering efficiently
- No significant performance difference vs box captions

## Compatibility

- **FFmpeg**: Requires `libass` support (included in most builds)
- **Players**: Works in all modern video players
- **Browsers**: Native HTML5 video playback supported
- **Mobile**: iOS and Android compatible

## Related Documentation

- [IMAGES_GUIDE.md](./IMAGES_GUIDE.md) - Educational image overlays
- [CLAUDE.md](./CLAUDE.md) - Project overview and architecture
