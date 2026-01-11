# Educational Images Guide

This guide explains how to add educational images to your generated videos. Images can be synced to specific dialogue lines to enhance the learning experience.

## Overview

The image workflow allows you to:
1. Generate a transcript first (without creating videos)
2. Review and edit the transcript
3. Add image references to specific dialogue lines
4. Generate videos with the images overlaid

## API Workflow

### Step 1: Generate Transcript

```bash
POST /generate-transcript
```

**Form Data:**
- `source_type`: `youtube`, `audio`, `text`, or `pptx`
- `user_id`: User ID (default: 1)
- `content`: Text content or YouTube URL (for text/youtube types)
- `file`: Audio or PPTX file upload (for audio/pptx types)

**Response:**
```json
{
  "transcript_id": "abc123...",
  "expires_in_hours": 24,
  "subtopic_count": 3,
  "subtopic_transcripts": [
    {
      "subtopic_title": "Introduction",
      "dialogue": [
        {
          "caption": "Hey Stewie, did you know about photosynthesis?",
          "speaker": "PETER",
          "line_number": 1,
          "duration_estimate": 2.4
        },
        ...
      ]
    }
  ]
}
```

### Step 2: Add Image References

Edit the transcript JSON to add `image` fields to specific dialogue lines:

```json
{
  "subtopic_transcripts": [
    {
      "subtopic_title": "Introduction",
      "dialogue": [
        {
          "caption": "Hey Stewie, did you know about photosynthesis?",
          "speaker": "PETER"
        },
        {
          "caption": "Look at this diagram showing how plants convert sunlight!",
          "speaker": "STEWIE",
          "image": {
            "filename": "photosynthesis_diagram.png",
            "size": "large"
          }
        }
      ]
    }
  ]
}
```

### Step 3: Generate Video with Images

```bash
POST /generate-video-with-images
```

**Form Data:**
- `transcript_id`: The ID from Step 1
- `user_id`: User ID (default: 1)
- `images[]`: Upload image files (multipart)
- `updated_transcript`: The modified transcript JSON with image references

**Response:**
```json
{
  "collection_id": 42,
  "video_count": 3,
  "results": [
    {
      "subtopic_title": "Introduction",
      "video_path": "assets/output/...",
      "video_id": 123
    }
  ]
}
```

## Image Configuration Options

Each dialogue line can have an optional `image` field:

```json
{
  "image": {
    "filename": "diagram.png",    // Required: must match uploaded file
    "size": "medium",             // Optional: "medium" (432px) or "large" (800px)
    "start_time": 0.5,            // Optional: seconds after line starts (default: 0)
    "duration": 3.0               // Optional: how long to show (default: entire line)
  }
}
```

### Size Options

| Size   | Width  | Position     | Use Case                    |
|--------|--------|--------------|------------------------------|
| medium | 432px  | Top-right    | Diagrams, charts, icons     |
| large  | 800px  | Top-center   | Full illustrations, photos  |

### Timing Options

- **Default behavior**: Image shows for the entire duration of the dialogue line
- **start_time**: Delay (in seconds) before image appears after line starts
- **duration**: How long the image stays visible (capped at line end)

## Image Requirements

- **Formats**: PNG, JPG, JPEG, GIF
- **Max size**: 10MB per image
- **Recommended**: PNG with transparent background for best results

## Example: Complete Workflow

```bash
# 1. Generate transcript from text
curl -X POST http://localhost:8000/generate-transcript \
  -F "source_type=text" \
  -F "user_id=1" \
  -F "content=Photosynthesis is the process by which plants convert sunlight..."

# Response: {"transcript_id": "abc123", ...}

# 2. Retrieve transcript to review
curl http://localhost:8000/transcripts/abc123

# 3. Generate video with images
curl -X POST http://localhost:8000/generate-video-with-images \
  -F "transcript_id=abc123" \
  -F "user_id=1" \
  -F "images[]=@photosynthesis_diagram.png" \
  -F "images[]=@plant_cell.png" \
  -F 'updated_transcript={
    "subtopic_transcripts": [
      {
        "subtopic_title": "Photosynthesis",
        "dialogue": [
          {"caption": "Plants are amazing!", "speaker": "PETER"},
          {"caption": "Look at this diagram!", "speaker": "STEWIE", "image": {"filename": "photosynthesis_diagram.png", "size": "large"}}
        ]
      }
    ]
  }'
```

## Visual Layout

The video layout places:
- **Characters**: Bottom-left (both Peter and Stewie)
- **Captions**: Center of screen
- **Educational images**: Top area (right for medium, center for large)

```
+----------------------------------+
|           [LARGE IMAGE]          |  <- large: centered
|                    [MED IMAGE]   |  <- medium: top-right
|                                  |
|                                  |
|          [ CAPTION TEXT ]        |
|                                  |
| [CHARACTER]                      |
+----------------------------------+
```

## Effects

Images include automatic visual effects:
- **Fade in**: 0.3 second fade when appearing
- **Fade out**: 0.3 second fade when disappearing
- **Aspect ratio**: Maintained (only width is constrained)

## Troubleshooting

### "Referenced images not found in upload"
Ensure the `filename` in your transcript matches exactly with the uploaded file name.

### "Transcript not found or expired"
Transcripts expire after 24 hours. Generate a new transcript if needed.

### "Image too large"
Reduce image file size to under 10MB.

### Image not appearing
- Check that the `filename` matches exactly (case-sensitive)
- Verify the image format is supported (PNG, JPG, JPEG, GIF)
- Ensure `start_time` + `duration` falls within the dialogue line's duration
