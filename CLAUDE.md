# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI application that generates educational videos from various input sources (YouTube, audio, PowerPoint, text). The pipeline extracts content, generates scripts using Gemini AI, creates audio via MiniMax TTS, and assembles videos with FFmpeg.

## Commands

```bash
# Start development server
uvicorn main:app --reload

# Run tests
pytest tests/ -v

# Run specific test file
pytest tests/test_subtopics.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# CLI usage (complete collection pipeline)
python cli.py --source lecture.mp3 --source-type audio --user-id 1
python cli.py --source notes.txt --source-type text
python cli.py --source "https://youtube.com/watch?v=..." --source-type youtube

# Docker - Development (with local PostgreSQL)
docker compose --profile dev up -d

# Docker - Production (with external Neon DB)
docker compose --profile prod-only up -d

# Docker build only
docker compose build
```

## Environment Variables

Required in `.env` (see `.env.example`):
- `GEMINI_API_KEY` - Google Gemini API key for script generation
- `MINIMAX_API_KEY` - MiniMax API key for TTS
- `MINIMAX_GROUP_ID` - MiniMax group ID for authentication
- `MINIMAX_PETER_VOICE`, `MINIMAX_STEWIE_VOICE` - MiniMax voice IDs
- `DATABASE_URL` - PostgreSQL connection string (Neon for prod, local for dev)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` - For S3 video storage

Note: YouTube transcript extraction uses `youtube-transcript-api` (no API key required)

## Architecture

### Two-Pipeline Design

The project separates fast operations (frontend) from slow, I/O-intensive operations (backend):

**Frontend Pipeline** (`frontend_pipeline/`):
- `script_generation/transcripts.py` - Extracts single dialogue from sources
- `script_generation/prompts.py` - Gemini prompt templates for content extraction
- `script_generation/models.py` - Pydantic models (SingleDialogue, TranscriptResponse)
- `script_generation/youtube.py` - YouTube transcript extraction helper

**Backend Pipeline** (`backend_pipeline/`):
- `audio_generation/minimax_tts.py` - TTS for videos using MiniMax API
- `video_assembly/ffMpeg.py` - Video assembly with FFmpeg
- `generate_video.py` - Orchestrates single video creation (replaces generate_subtopic_videos.py)

### Entry Points

- `main.py` - FastAPI application with all API endpoints
- `cli.py` - Command-line interface for batch processing

### Data Flow

```
Input (YouTube/Audio/PPTX/Text)
    ↓
extract_transcripts() → SingleDialogue (~1 minute conversation)
    ↓
generate_video_from_dialogue() → Single video uploaded to S3
    ↓
Saved to collection in PostgreSQL (one video per transcript)
```

### Database Layer (`services/`)

- `video_service.py` - Video CRUD and S3 upload
- `collection_service.py` - Collection management
- `account_service.py` - User accounts
- `progress_service.py` - Job progress tracking with WebSocket support

### Key Models

**New Single Dialogue Format:**
```json
{
  "dialogue_data": {
    "title": "Conversation Title",
    "dialogue": [
      {
        "caption": "Short sentence under 20 words",
        "speaker": "PETER",
        "emotion": "neutral",
        "image": {  // optional
          "filename": "diagram.png",
          "size": "medium",
          "start_time": 0.5,
          "duration": 3.0
        }
      }
    ]
  }
}
```

**Legacy Format** (deprecated, kept for backward compatibility):
- `SubtopicDialogue` - Old multi-video format

## API Endpoints

### Job-Based Video Generation (Async with WebSocket Progress)

The API uses an async job-based architecture with real-time progress tracking via WebSocket:

**Transcript Generation:**
- `POST /jobs/generate-transcript` - Start transcript generation job (returns `job_id`)
- `WS /ws/progress/{job_id}` - WebSocket for real-time progress updates
- `GET /jobs/{job_id}/progress` - HTTP fallback for polling progress

**Video Generation:**
- `POST /jobs/generate-video` - Start video generation from transcript (returns `job_id`)
- Uses same WebSocket/HTTP progress endpoints

**Data Endpoints:**
- `GET /videos` - User videos grouped by collection
- `GET /collections` - List user collections
- `GET /collections/{id}` - Collection details with videos
- `POST /accounts` - Create user account
- `POST /accounts/login` - Authenticate user

## Educational Images Feature

Videos can include educational images overlaid during specific dialogue lines.

**Workflow:**
1. `POST /jobs/generate-transcript` - Start transcript generation (async)
2. Connect to WebSocket `/ws/progress/{job_id}` for progress
3. Get `transcript_id` from completed result
4. Add `image` references to dialogue lines in the JSON
5. `POST /jobs/generate-video` with `transcript_id` and images

### Image Sizes and Positions

| Size | Width | Available Positions | Default |
|------|-------|---------------------|---------|
| small | 300px | top-left, top-right, bottom-right | top-right |
| medium | 600px | top-left, top-right | top-right |
| large | 800px | top-center | top-center |

**Limits:** 1 large OR 2 medium images (top area), AND up to 3 small images simultaneously

**API Endpoint:** `GET /images/positions` - Returns all sizes, positions, and limits

### Image Configuration Examples

**Single image (basic):**
```json
{
  "caption": "Look at this diagram!",
  "speaker": "STEWIE",
  "image": {
    "filename": "diagram.png",
    "size": "medium",
    "position": "top-right",
    "start_time": 0.5,
    "duration": 3.0
  }
}
```

**Two medium images (side by side):**
```json
{
  "caption": "Compare these diagrams!",
  "speaker": "PETER",
  "image": {
    "filename": "before.png",
    "size": "medium",
    "position": "top-left"
  }
}
// Another dialogue line with:
{
  "image": {
    "filename": "after.png",
    "size": "medium", 
    "position": "top-right"
  }
}
```

**Small image next to character:**
```json
{
  "caption": "Check this icon!",
  "speaker": "STEWIE",
  "image": {
    "filename": "icon.png",
    "size": "small",
    "position": "bottom-right"
  }
}
```

**Video Layout:**
```
┌─────────────────────────────────────────┐
│ [SMALL]   [MEDIUM/LARGE]      [SMALL]  │  ← Top (y=100px)
│ top-left     top area        top-right │
│                                         │
│            [CAPTIONS]                   │  ← Center
│                                         │
│ [CHAR]                        [SMALL]  │  ← Bottom
│ [CHAR]                     bottom-right│
│ left side                               │
└─────────────────────────────────────────┘
```

## Karaoke Caption Mode

Videos use karaoke-style captions by default, with word-by-word yellow highlighting. See `KARAOKE_GUIDE.md` for complete documentation.

**Caption Modes:**
- **Karaoke (default)**: Words highlight yellow one-by-one as spoken
- **Box**: Traditional white text in semi-transparent black boxes

**API Usage:**
```bash
# Default (karaoke ON)
curl -X POST http://localhost:8000/jobs/generate-video \
  -F "transcript_id=abc123" \
  -F "user_id=1"

# Disable karaoke (use box captions)
curl -X POST http://localhost:8000/jobs/generate-video \
  -F "transcript_id=abc123" \
  -F "user_id=1" \
  -F "karaoke_captions=false"
```

**CLI Testing:**
```bash
# Test karaoke mode
python test_image_overlay.py --config test_configs/my_config.json --karaoke

# Test box captions
python test_image_overlay.py --config test_configs/my_config.json
```

## Testing

Tests are organized by feature in `tests/`:
- `test_subtopics.py` - Subtopic extraction and video generation
- `test_collections.py` - Collection CRUD operations
- `test_api.py` - FastAPI endpoint tests
- `test_youtube.py` - YouTube transcript extraction

Shared fixtures in `conftest.py` mock external services (Gemini, MiniMax, DB, S3, FFmpeg).

## Docker Setup

- `Dockerfile` - Python 3.11 + FFmpeg + dependencies
- `docker-compose.yml` - Two profiles:
  - `dev`: App + local PostgreSQL
  - `prod-only`: App only (uses external Neon DB)

## Asset Directories

- `assets/videos/` - Background video files (.mp4)
- `assets/characters/` - Character images (peter.png, etc.)
- `assets/audio/generated/` - Generated TTS audio
- `assets/output/` - Final assembled videos
