# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI application that generates educational videos from various input sources (YouTube, audio, PowerPoint, text). The pipeline extracts content, generates scripts using Gemini AI, creates audio via ElevenLabs TTS, and assembles videos with FFmpeg.

## Commands

```bash
# Start development server
uvicorn main:app --reload

# Run complete collection pipeline test
python test_complete_collection.py

# Test quiz pipeline
python test_quiz_pipeline.py --input <file> --type <audio|text|youtube>

# Run quiz API tests
python test_quiz_api.py --input <file> --type <type>
```

## Environment Variables

Required in `.env` (see `.env.example`):
- `Gemini_API_Key` - Google Gemini API key for script generation
- `ELEVENLABS_API_KEY` - ElevenLabs API key for TTS
- `Peter_voiceId`, `Stewie_voiceId` - ElevenLabs voice IDs
- `DATABASE_URL` - PostgreSQL connection string (Neon)
- `RapidAPI_Key` - For YouTube transcript extraction

## Architecture

### Two-Pipeline Design

The project separates fast operations (frontend) from slow, I/O-intensive operations (backend):

**Frontend Pipeline** (`frontend_pipeline/`):
- `script_generation/transcripts.py` - Extracts subtopic and quiz transcripts from sources
- `script_generation/prompts.py` - Gemini prompt templates for content extraction
- `script_generation/models.py` - Pydantic models for script structure

**Backend Pipeline** (`backend_pipeline/`):
- `audio_generation/elevenLabs.py` - TTS for subtopic videos
- `audio_generation/elevenLabs_quiz.py` - TTS with pause handling for quiz videos
- `video_assembly/ffMpeg.py` - Video assembly for subtopics
- `video_assembly/ffMpeg_quiz.py` - Video assembly with quiz timing
- `generate_subtopic_videos.py` - Orchestrates subtopic video creation
- `generate_quiz_video.py` - Orchestrates quiz video creation
- `generate_complete_collection.py` - Full pipeline: subtopics + quiz → collection

### Data Flow

```
Input (YouTube/Audio/PPTX/Text)
    ↓
extract_transcripts() → List[SubtopicPayload]
    ↓
generate_videos_from_subtopic_list() → Videos uploaded to S3
    ↓
extract_quiz_transcripts() → List[QuizModule]
    ↓
generate_quiz_video() → Quiz video uploaded to S3
    ↓
All saved to same collection in PostgreSQL
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

Quiz questions include `ask` and `reveal` scripts (<25 words each) with timing for pauses before reveals.

## API Endpoints

- `POST /generate-video` - Generate subtopic + quiz videos from source
- `POST /generate-complete-collection` - Full collection from single source
- `POST /extract-quiz-transcripts` - Extract quiz JSON only
- `POST /generate-quiz-video` - Generate video from quiz JSON
- `GET /videos` - User videos grouped by collection
- `GET /collections` - List user collections
- `GET /collections/{id}` - Collection details with videos

## Asset Directories

- `assets/videos/` - Background video files (.mp4)
- `assets/characters/` - Character images (peter.png, etc.)
- `assets/audio/generated/` - Generated TTS audio
- `assets/output/` - Final assembled videos
