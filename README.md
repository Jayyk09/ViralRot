# Video Generation API

A FastAPI application that generates videos from slides using OCR, Gemini AI, ElevenLabs TTS, and FFmpeg.

## Architecture Pipeline

```
Input (Slides) 
    ↓
[OCR] Extract text → Raw transcript
    ↓
[Gemini] Generate script → [{t, c, s}, {t, c, s}, ...]
    ↓
[ElevenLabs] Generate audio + timing → Shot list with durations
    ↓
[FFmpeg] Assemble video → Final video with synchronized captions
```

### Script Format
- `t`: Full line for speaker to say
- `c`: Short caption for screen
- `s`: Speaker ID (for voice selection)

## Project Structure

```
HackEmory/
├── main.py                              # Basic FastAPI app
├── frontend_pipeline/                   # Quick pipeline (OCR → Script)
│   ├── ocr/                            # Slide text extraction
│   ├── script_generation/              # Gemini script generation
│   └── shared/                         # Shared frontend utilities
└── backend_pipeline/                    # Slow pipeline (Audio → Video)
    ├── audio_generation/               # ElevenLabs TTS + timing
    ├── video_assembly/                 # FFmpeg video editing
    └── shared/                         # Shared backend utilities
```

## Team Workflow

### Developer 1: Frontend Pipeline (Fast)
**Focus**: `frontend_pipeline/`
- **OCR**: Extract text from slides
- **Script Gen**: Call Gemini to generate structured script

### Developer 2: Backend Pipeline (Slow - Takes Time!)
**Focus**: `backend_pipeline/`
- **Audio Gen**: Loop through script, call ElevenLabs, measure timing with ffprobe
- **Video Assembly**: Concatenate audio, sync captions with FFmpeg

## Why This Structure?

The backend pipeline (audio + video) is **time-intensive**:
- Multiple API calls to ElevenLabs (one per line)
- ffprobe measurements for each audio file
- Complex FFmpeg filter chains

By separating folders, both developers can work in parallel without conflicts!

## Quick Start

```bash
# Run the basic FastAPI app
uvicorn main:app --reload

# Visit http://localhost:8000
```
