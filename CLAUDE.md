# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI application that generates educational videos from various input sources (YouTube, audio, PowerPoint, text). The pipeline extracts content, generates scripts using Gemini AI, creates audio via ElevenLabs TTS, and assembles videos with FFmpeg.

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
- `ELEVENLABS_API_KEY` - ElevenLabs API key for TTS
- `Peter_voiceId`, `Stewie_voiceId` - ElevenLabs voice IDs
- `DATABASE_URL` - PostgreSQL connection string (Neon for prod, local for dev)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` - For S3 video storage

Note: YouTube transcript extraction uses `youtube-transcript-api` (no API key required)

## Architecture

### Two-Pipeline Design

The project separates fast operations (frontend) from slow, I/O-intensive operations (backend):

**Frontend Pipeline** (`frontend_pipeline/`):
- `script_generation/transcripts.py` - Extracts subtopic transcripts from sources
- `script_generation/prompts.py` - Gemini prompt templates for content extraction
- `script_generation/models.py` - Pydantic models for script structure
- `script_generation/youtube.py` - YouTube transcript extraction helper

**Backend Pipeline** (`backend_pipeline/`):
- `audio_generation/elevenLabs.py` - TTS for subtopic videos
- `video_assembly/ffMpeg.py` - Video assembly for subtopics
- `generate_subtopic_videos.py` - Orchestrates subtopic video creation

### Entry Points

- `main.py` - FastAPI application with all API endpoints
- `cli.py` - Command-line interface for batch processing

### Data Flow

```
Input (YouTube/Audio/PPTX/Text)
    ↓
extract_transcripts() → List[SubtopicPayload]
    ↓
generate_videos_from_subtopic_list() → Videos uploaded to S3
    ↓
All saved to collection in PostgreSQL
```

### Database Layer (`save_to_db/`)

- `save_video.py` - Video CRUD and S3 upload
- `collection_service.py` - Collection management
- `account_service.py` - User accounts

### Key Models

Script format uses `{t, c, s}` structure:
- `t`: Full line for speaker (TTS input)
- `c`: Short caption for screen
- `s`: Speaker ID (Peter/Stewie)

## API Endpoints

- `POST /generate-video` - Generate subtopic videos from source
- `GET /videos` - User videos grouped by collection
- `GET /collections` - List user collections
- `GET /collections/{id}` - Collection details with videos
- `POST /accounts` - Create user account
- `POST /accounts/login` - Authenticate user

## Testing

Tests are organized by feature in `tests/`:
- `test_subtopics.py` - Subtopic extraction and video generation
- `test_collections.py` - Collection CRUD operations
- `test_api.py` - FastAPI endpoint tests
- `test_youtube.py` - YouTube transcript extraction

Shared fixtures in `conftest.py` mock external services (Gemini, ElevenLabs, DB, S3, FFmpeg).

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
