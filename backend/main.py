import asyncio
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from typing import Literal

from services.audio_service import AudioService
from services.video_service import VideoService, get_collection_videos
from services.collection_service import create_collection, get_collection, get_user_collections, find_last_collection
from services.progress_service import ProgressService, set_event_loop
from services.repositories.editor_repository import (
    EditorInvalidOrderError,
    EditorLineGeneratingError,
    EditorProjectNotFoundError,
    EditorRepository,
    EditorRevisionConflictError,
)
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_video import (
    generate_video_from_dialogue,
    generate_audio_for_dialogue,
    get_background_video,
    get_background_video_from_storage,
    slugify,
)
from backend_pipeline.video_assembly.ffMpeg import create_video_with_audio_and_captions

from storage.factory import get_storage_backend

BACKEND_DIR = Path(__file__).resolve().parent

DIRS = {
    "background_videos": BACKEND_DIR / "assets" / "videos",
    "output": BACKEND_DIR / "assets" / "output",
    "temp_upload": BACKEND_DIR / "tmp" / "uploads",
    "temp_images": BACKEND_DIR / "tmp" / "uploads" / "images",
    "generated_audio": BACKEND_DIR / "assets" / "audio" / "generated",
}

for dir in DIRS.values():
    dir.mkdir(parents=True, exist_ok=True)

# ============ Pydantic Models ============

class ImageConfig(BaseModel):
    """Configuration for educational image overlay."""
    filename: str
    size: Literal["medium", "large"] = "medium"
    start_time: Optional[float] = None
    duration: Optional[float] = None


class DialogueLine(BaseModel):
    caption: str
    speaker: str
    image: Optional[ImageConfig] = None


class DialoguePayload(BaseModel):
    """Single dialogue with title and dialogue lines."""
    title: str
    dialogue: List[DialogueLine]


class TranscriptGenerationRequest(BaseModel):
    """Request to generate a transcript from a source."""
    pass  # No request body needed, uses form data


class VideoGenerationRequest(BaseModel):
    """Request to generate video from a dialogue."""
    dialogue: DialoguePayload
    images: Optional[Dict[str, str]] = None
    background_video: Optional[str] = "minecraft.mp4"
    karaoke_captions: bool = True  # Default ON: word-by-word yellow highlighting


class EditorProjectGenerateRequest(BaseModel):
    description: str
    background_video_id: str


class EditorProjectUpdate(BaseModel):
    title: str
    background_video_id: Optional[str] = None
    expected_revision: int


class EditorLineCreate(BaseModel):
    caption: str
    speaker: str
    emotion: Optional[str] = None
    position: Optional[int] = None
    expected_project_revision: int


class EditorLineUpdate(BaseModel):
    caption: str
    speaker: str
    emotion: Optional[str] = None
    expected_revision: int


class EditorLineDelete(BaseModel):
    expected_project_revision: int


class EditorLineOrderUpdate(BaseModel):
    line_ids: List[UUID]
    expected_project_revision: int


class EditorVideoGenerateRequest(BaseModel):
    karaoke_captions: bool = True

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle handler for startup and shutdown tasks."""
    # Startup: Store event loop reference for thread-safe progress updates
    loop = asyncio.get_running_loop()
    set_event_loop(loop)
    print(f"✅ Event loop initialized for progress broadcasting")
    
    yield
    
    # Shutdown: Clean up expired jobs and transcripts
    expired_jobs = ProgressService.cleanup_expired()


editor_repository = EditorRepository()


app = FastAPI(
    title="Video Generation API",
    description="API for generating videos from slides",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS settings so React (localhost:3000) can talk to this API
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # or ["*"] during dev if you want to be lazy
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Opt-in local development fixtures. Generated media stays untracked and is
# never exposed by production unless ENABLE_DEV_FIXTURES is explicitly set.
if os.getenv("ENABLE_DEV_FIXTURES", "false").lower() == "true":
    dev_fixtures_dir = BACKEND_DIR / "dev_fixtures"
    dev_fixtures_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/dev/fixtures",
        StaticFiles(directory=str(dev_fixtures_dir)),
        name="dev_fixtures",
    )

@app.get("/")
async def root():
    return {
        "message": "Video Generation API",
        "status": "running",
        "pipeline": {
            "frontend": ["Script Generation"],
            "backend": ["Audio Generation", "Video Assembly"]
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/images/positions")
async def get_image_positions():
    """
    Get available image sizes and their valid positions.
    
    Useful for frontend validation and UI hints when adding educational images.
    
    Image Limits:
    - 1 large image OR 2 medium images (mutually exclusive for top area)
    - Up to 3 small images can be added alongside large/medium
    
    Returns:
        Dictionary mapping sizes to available positions with descriptions and coordinates
    """
    return {
        "small": {
            "size_px": 300,
            "description": "Icon-size images, flexible positioning",
            "max_count": 3,
            "positions": {
                "top-left": {
                    "description": "Top-left corner, 50px margin",
                    "coordinates": {"x": "50", "y": "100"}
                },
                "top-right": {
                    "description": "Top-right corner, 50px margin (default)",
                    "coordinates": {"x": "W-w-50", "y": "100"}
                },
                "bottom-right": {
                    "description": "Bottom-right, next to characters",
                    "coordinates": {"x": "W-w-50", "y": "H-h-50"}
                }
            },
            "default_position": "top-right"
        },
        "medium": {
            "size_px": 600,
            "description": "Mid-size diagrams, top corners",
            "max_count": 2,
            "positions": {
                "top-left": {
                    "description": "Top-left corner, 50px margin",
                    "coordinates": {"x": "50", "y": "100"}
                },
                "top-right": {
                    "description": "Top-right corner, 50px margin (default)",
                    "coordinates": {"x": "W-w-50", "y": "100"}
                }
            },
            "default_position": "top-right"
        },
        "large": {
            "size_px": 800,
            "description": "Full-width diagrams, top-center",
            "max_count": 1,
            "positions": {
                "top-center": {
                    "description": "Top-center, horizontally centered",
                    "coordinates": {"x": "(W-w)/2", "y": "100"}
                }
            },
            "default_position": "top-center"
        },
        "limits": {
            "description": "1 large OR 2 medium images, AND up to 3 small images",
            "rules": [
                "Large and medium images share the top area - use one OR the other",
                "Small images can be combined with any large/medium configuration",
                "Maximum 3 small images at any time",
                "Images at same position will overlap - use different positions"
            ]
        },
        "video_dimensions": {
            "width": 1080,
            "height": 1920,
            "aspect_ratio": "9:16 (portrait)"
        }
    }


# ============ WebSocket Progress Endpoint ============

def get_current_user_id() -> int:
    """Get current user ID. OpenSource local env: no need for dev"""
    return 1


@app.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time job progress updates.
    
    Connect to this endpoint after starting a video/transcript generation job
    to receive real-time progress updates.
    
    Message format:
    {
        "type": "progress" | "completed" | "error",
        "job_id": "abc123",
        "job_type": "transcript_generation" | "video_generation",
        "status": "queued" | "processing" | "completed" | "failed",
        "percentage": 45,
        "message": "Generating audio for subtopic 2/5...",
        "current_stage": "audio_generation",
        "current_subtopic": 2,  // video jobs only
        "total_subtopics": 5,   // video jobs only
        "result": {...},        // on completion
        "error": "..."          // on failure
    }
    """
    await websocket.accept()
    
    # Verify job exists
    job = ProgressService.get_job(job_id)
    if not job:
        await websocket.send_json({
            "type": "error",
            "job_id": job_id,
            "error": "Job not found or expired"
        })
        await websocket.close()
        return
    
    # Register connection
    ProgressService.add_websocket(job_id, websocket)
    
    # Send current state immediately
    initial_update = ProgressService.get_initial_update(job)
    await websocket.send_text(initial_update.model_dump_json())
    
    try:
        # Keep connection alive until client disconnects
        # Also handle ping/pong for connection health
        while True:
            try:
                # Wait for messages (client might send pings)
                message = await websocket.receive_text()
                # Echo back for ping/pong
                if message == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    finally:
        ProgressService.remove_websocket(job_id, websocket)


@app.get("/jobs/{job_id}/progress")
async def get_job_progress(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """
    HTTP fallback to check job progress without WebSocket.
    
    Use this endpoint for polling if WebSocket is not available.
    Poll every 1-2 seconds for responsive updates.
    
    Returns:
        Current progress state including percentage, stage, and result (if completed).
    """
    job = ProgressService.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    
    # Verify ownership
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    
    response = {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "percentage": job.percentage,
        "message": job.message,
        "current_stage": job.current_stage,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
    }
    
    # Add video-specific fields
    if job.job_type == "video_generation":
        response["current_subtopic"] = getattr(job, "current_subtopic", None)
        response["total_subtopics"] = getattr(job, "total_subtopics", None)
    
    # Include result only when completed
    if job.status == "completed":
        response["result"] = job.result
    
    return response


async def _run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


# ============ Editor Persistence Endpoints ============

@app.post("/editor/projects", status_code=202)
async def create_editor_project(
    payload: EditorProjectGenerateRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    """Generate and persist a project from user-provided source material."""
    description = payload.description.strip()
    background_video_id = payload.background_video_id.strip()
    if not description:
        raise HTTPException(status_code=422, detail="Description cannot be blank")
    if not background_video_id:
        raise HTTPException(status_code=422, detail="Background video is required")

    job_id = ProgressService.create_transcript_job(user_id=user_id)
    background_tasks.add_task(
        _process_transcript_job,
        job_id=job_id,
        user_id=user_id,
        description=description,
        background_video_id=background_video_id,
    )
    return {
        "job_id": job_id,
        "job_type": "transcript_generation",
        "message": "Project generation started.",
        "websocket_url": f"/ws/progress/{job_id}",
        "status_url": f"/jobs/{job_id}/progress",
    }


@app.get("/editor/projects/{project_id}")
async def get_editor_project(
    project_id: UUID,
    user_id: int = Depends(get_current_user_id),
):
    try:
        project = await _run_blocking(
            editor_repository.get_project, project_id, user_id
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="Editor project not found")
    return {"project": project}


@app.patch("/editor/projects/{project_id}")
async def update_editor_project(
    project_id: UUID,
    payload: EditorProjectUpdate,
    user_id: int = Depends(get_current_user_id),
):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Project title cannot be blank")
    if payload.expected_revision < 1:
        raise HTTPException(status_code=422, detail="expected_revision must be at least 1")
    try:
        project = await _run_blocking(
            editor_repository.update_project,
            project_id,
            user_id,
            title,
            payload.background_video_id.strip() if payload.background_video_id else None,
            payload.expected_revision,
        )
        return {"project": project}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EditorRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/editor/projects/{project_id}/lines", status_code=201)
async def add_editor_line(
    project_id: UUID,
    payload: EditorLineCreate,
    user_id: int = Depends(get_current_user_id),
):
    caption = payload.caption.strip()
    speaker = payload.speaker.strip()
    if not caption or not speaker:
        raise HTTPException(status_code=422, detail="Caption and speaker cannot be blank")
    try:
        project = await _run_blocking(
            editor_repository.add_line,
            project_id,
            user_id,
            {
                "caption": caption,
                "speaker": speaker,
                "emotion": payload.emotion.strip() if payload.emotion else None,
            },
            payload.position,
            payload.expected_project_revision,
        )
        return {"project": project}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EditorRevisionConflictError, EditorInvalidOrderError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/editor/projects/{project_id}/lines/order")
async def reorder_editor_lines(
    project_id: UUID,
    payload: EditorLineOrderUpdate,
    user_id: int = Depends(get_current_user_id),
):
    try:
        project = await _run_blocking(
            editor_repository.reorder_lines,
            project_id,
            user_id,
            payload.line_ids,
            payload.expected_project_revision,
        )
        return {"project": project}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EditorRevisionConflictError, EditorInvalidOrderError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/editor/projects/{project_id}/lines/{line_id}")
async def delete_editor_line(
    project_id: UUID,
    line_id: UUID,
    payload: EditorLineDelete,
    user_id: int = Depends(get_current_user_id),
):
    try:
        project = await _run_blocking(
            editor_repository.delete_line,
            project_id,
            line_id,
            user_id,
            payload.expected_project_revision,
        )
        return {"project": project}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EditorRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/editor/projects/{project_id}/lines/{line_id}")
async def update_editor_line(
    project_id: UUID,
    line_id: UUID,
    payload: EditorLineUpdate,
    user_id: int = Depends(get_current_user_id),
):
    caption = payload.caption.strip()
    speaker = payload.speaker.strip()
    if not caption or not speaker:
        raise HTTPException(status_code=422, detail="Caption and speaker cannot be blank")
    if payload.expected_revision < 1:
        raise HTTPException(status_code=422, detail="expected_revision must be at least 1")

    try:
        line = await _run_blocking(
            editor_repository.update_line,
            project_id,
            line_id,
            user_id,
            caption,
            speaker,
            payload.emotion.strip() if payload.emotion else None,
            payload.expected_revision,
        )
        return {"line": line}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EditorRevisionConflictError, EditorLineGeneratingError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ============ Async Job Endpoints (with Progress Tracking) ============

async def _process_transcript_job(
    job_id: str,
    user_id: int,
    description: str,
    background_video_id: str,
):
    """Background task for transcript generation with progress updates."""
    try:
        # Stage 1: Extracting content
        ProgressService.update_job(
            job_id=job_id,
            status="processing",
            current_stage="extracting_content",
        )
        
        # Small delay to allow WebSocket connection
        await asyncio.sleep(0.1)
        
        # Stage 2: Generating dialogue
        ProgressService.update_job(
            job_id=job_id,
            current_stage="generating_dialogue",
        )
        
        # Call the transcript extraction - returns SingleDialogue now
        dialogue = await _run_blocking(
            extract_transcripts,
            description,
            "text",
        )
        
        if not dialogue or not dialogue.dialogue:
            ProgressService.update_job(
                job_id=job_id,
                status="failed",
                error="No dialogue generated from source content. The AI model returned empty results.",
            )
            return
        
        # Persist Gemini's output before exposing it to the editor. The browser
        # receives a project ID, loads that project, and sends only later edits.
        generated_dialogue = dialogue.model_dump()
        project = await _run_blocking(
            editor_repository.create_project,
            user_id,
            generated_dialogue["title"],
            background_video_id,
            [
                {
                    "caption": line["caption"],
                    "speaker": line["speaker"],
                    "emotion": line.get("emotion"),
                }
                for line in generated_dialogue["dialogue"]
            ],
        )

        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={"project_id": str(project["id"])},
        )
    
    except Exception as e:
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(e).__name__}: {str(e)}",
        )
    


@app.post("/editor/projects/{project_id}/video", status_code=202)
async def create_video_job(
    project_id: UUID,
    payload: EditorVideoGenerateRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    """Generate a video from the current persisted project revision."""
    try:
        project = await _run_blocking(
            editor_repository.get_project, project_id, user_id
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="Editor project not found")
    if not project["dialogue"]:
        raise HTTPException(status_code=409, detail="Project has no dialogue lines")
    video = project["background_video_id"]
    if not video:
        raise HTTPException(status_code=409, detail="Project has no background video")

    dialogue_data = {
        "title": project["title"],
        "dialogue": project["dialogue"],
    }
    transcript_data = {"dialogue": dialogue_data}
    session_id = uuid4().hex
    job_id = ProgressService.create_video_job(
        user_id=user_id,
        dialogue_title=str(project["title"]),
    )
    background_tasks.add_task(
        _process_video_job,
        job_id=job_id,
        user_id=user_id,
        video=str(video),
        transcript_data=transcript_data,
        image_dir=None,
        session_id=session_id,
        karaoke_captions=payload.karaoke_captions,
    )
    return {
        "job_id": job_id,
        "job_type": "video_generation",
        "dialogue_title": project["title"],
        "karaoke_captions": payload.karaoke_captions,
        "message": "Video generation started.",
        "websocket_url": f"/ws/progress/{job_id}",
        "status_url": f"/jobs/{job_id}/progress",
    }


async def _process_video_job(
    job_id: str,
    user_id: int,
    video: str,
    transcript_data: dict,
    image_dir: Optional[str],
    session_id: str,
    karaoke_captions: bool = True,
):
    """Background task for video generation with progress updates.
    
    Args:
        job_id: Unique job identifier for progress tracking
        user_id: User ID for database operations
        transcript_data: Dict with dialogue_data containing title and dialogue
        image_dir: Optional path to uploaded images directory
        session_id: Unique session ID for temp file management
        karaoke_captions: If True (default), use karaoke-style word-by-word highlighting.
                         If False, use traditional box captions.
    """
    try:
        _validate_background_video()
        
        # Update status to processing
        ProgressService.update_job(
            job_id=job_id,
            status="processing",
            current_stage="preparing_assets",
        )
        
        # Small delay to allow WebSocket connection
        await asyncio.sleep(0.1)
        
        # Extract dialogue data (support both keys)
        dialogue_data = transcript_data.get("dialogue") or transcript_data.get("dialogue_data")
        
        # Generate single video with progress callback
        session_id_full = uuid4().hex
        video_output_dir = DIRS["output"] / f"job_{session_id_full}"
        audio_output_dir = DIRS["generated_audio"] / f"job_{session_id_full}"
        
        # Progress callback wrapper for single video
        def progress_callback(job_id, current_stage, title):
            ProgressService.update_job(
                job_id=job_id,
                current_stage=current_stage,
            )
        
        # Debug logging for video generation
        print(f"\n{'='*50}")
        print(f"🎬 VIDEO GENERATION DEBUG")
        print(f"{'='*50}")
        print(f"  job_id: {job_id}")
        print(f"  image_dir: {image_dir}")
        print(f"  karaoke_captions: {karaoke_captions}")
        print(f"  dialogue_data keys: {dialogue_data.keys() if dialogue_data else 'None'}")
        dialogue_lines = dialogue_data.get('dialogue') if dialogue_data else None
        if dialogue_lines:
            print(f"  dialogue lines: {len(dialogue_lines)}")
            # Check for image references in dialogue (both single and array format)
            single_img_count = sum(1 for line in dialogue_lines if line.get('image'))
            array_img_count = sum(1 for line in dialogue_lines if line.get('images'))
            print(f"  lines with 'image': {single_img_count}")
            print(f"  lines with 'images' array: {array_img_count}")
            # Count total images in arrays
            total_array_images = sum(len(line.get('images') or []) for line in dialogue_lines)
            print(f"  total images in arrays: {total_array_images}")
        else:
            print(f"  dialogue lines: None or empty")
        print(f"{'='*50}\n")
        
        video_result = await _run_blocking(
            generate_video_from_dialogue,
            dialogue_data,
            DIRS["background_videos"],
            str(video_output_dir),
            str(audio_output_dir),
            user_id,
            video,
            None,  # collection_id (auto-create)
            image_dir,
            None,  # storage_backend
            progress_callback,  # progress_callback
            job_id,  # job_id for progress
            karaoke_captions,  # karaoke caption mode
        )
        
        # Get collection info
        collection_dict = await _run_blocking(find_last_collection, user_id)
        collection_id = collection_dict["id"] if collection_dict else None
        
        # Complete job
        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={
                "collection_id": collection_id,
                "video_id": video_result["video_id"],
                "title": video_result["title"],
                "access_url": video_result["access_url"],
                "storage_key": video_result["storage_key"],
            },
        )

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n{'='*60}")
        print(f"❌ VIDEO GENERATION ERROR")
        print(f"{'='*60}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {str(e)}")
        print(f"  Full traceback:\n{error_trace}")
        print(f"{'='*60}\n")
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(e).__name__}: {str(e)}",
        )

    finally:
        # Cleanup image dir
        if image_dir:
            image_path = Path(image_dir)
            if image_path.exists():
                shutil.rmtree(image_path, ignore_errors=True)


# ============ Audio-Only Generation + Minimal Export (Phase 1 pipeline split) ============
#
# These two endpoints split the monolithic /jobs/generate-video job in two:
# generate-audio finalizes narration + real timing data (no rendering), and
# export-video renders from that already-finalized audio (no TTS calls). This
# lets the frontend editor load real per-line/per-word timing before any
# overlay editing begins, instead of only having a duration estimate.

@app.post("/jobs/generate-audio")
async def create_audio_job(
    background_tasks: BackgroundTasks,
    user_id: int = Form(1),
    video: str = Form(..., description="Background video name (matches a file in the catalog)"),
    transcript: str = Form(..., description="Dialogue JSON, same shape as /jobs/generate-video"),
):
    """
    Generate narration audio + line/word timings from a dialogue transcript
    (ASYNC with progress tracking) - no final video is rendered here.

    Workflow:
    1. POST to this endpoint with transcript JSON and a background video name
    2. Poll GET /jobs/{job_id}/progress (or connect to the WebSocket)
    3. On completion, result contains everything the editor needs to preview
       and, later, export - no further TTS calls happen after this.

    Stages:
    - tts_generation: Per-line MiniMax TTS calls
    - concatenation: Stitch segments into one audio file, compute timings
    - uploading: Upload narration audio to storage

    Result format on completion:
        { "audio_url", "line_timings", "word_timestamps", "background_video_url" }
    """
    try:
        transcript_data = json.loads(transcript)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid transcript JSON")

    dialogue_data = transcript_data.get("dialogue") or transcript_data.get("dialogue_data")
    if not dialogue_data:
        raise HTTPException(status_code=400, detail="Transcript contains no dialogue data")

    dialogue_title = dialogue_data.get("title", "Untitled Dialogue")

    job_id = ProgressService.create_audio_job(user_id=user_id, dialogue_title=dialogue_title)

    background_tasks.add_task(
        _process_audio_job,
        job_id=job_id,
        user_id=user_id,
        video=video,
        dialogue_data=dialogue_data,
    )

    return {
        "job_id": job_id,
        "job_type": "audio_generation",
        "dialogue_title": dialogue_title,
        "message": "Audio generation started. Connect to WebSocket for progress.",
        "websocket_url": f"/ws/progress/{job_id}",
        "status_url": f"/jobs/{job_id}/progress",
    }


async def _process_audio_job(
    job_id: str,
    user_id: int,
    video: str,
    dialogue_data: dict,
):
    """Background task: TTS + concatenation only, no ffmpeg rendering."""
    try:
        _validate_background_video()

        ProgressService.update_job(job_id=job_id, status="processing", current_stage="tts_generation")
        await asyncio.sleep(0.1)

        dialogue = dialogue_data.get("dialogue") or []
        if not dialogue:
            raise ValueError("No dialogue found in transcript.")

        title = dialogue_data.get("title", "Untitled Dialogue")
        slug = slugify(title)
        session_id = uuid4().hex
        audio_output_dir = DIRS["generated_audio"] / f"job_{session_id}"

        audio_result = await _run_blocking(
            generate_audio_for_dialogue,
            dialogue,
            audio_output_dir,
            slug,
        )

        ProgressService.update_job(job_id=job_id, current_stage="concatenation")

        # Resolve the exact background file (get_background_video does fuzzy name
        # matching) so the presigned URL points at the same file used for export.
        background_path = await _run_blocking(_resolve_background_video, video)

        ProgressService.update_job(job_id=job_id, current_stage="uploading")

        storage = get_storage_backend()
        background_prefix = getattr(storage, "background_prefix", "")
        background_video_url = storage.generate_url(f"{background_prefix}{background_path.name}")

        audio_storage_key = f"audio/{user_id}/{session_id}.mp3"
        with open(audio_result["audio_file"], "rb") as audio_file:
            storage.upload(audio_file, audio_storage_key, {"content_type": "audio/mpeg"})
        audio_url = storage.generate_url(audio_storage_key)

        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={
                "audio_url": audio_url,
                "line_timings": audio_result["timings"],
                "word_timestamps": audio_result["word_timestamps"],
                "background_video_url": background_video_url,
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ AUDIO GENERATION ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(e).__name__}: {str(e)}",
        )


@app.post("/jobs/export-video")
async def create_export_job(
    background_tasks: BackgroundTasks,
    user_id: int = Form(1),
    video: str = Form(..., description="Background video name (same catalog entry used for generate-audio)"),
    audio_url: str = Form(..., description="URL of the already-generated narration audio from /jobs/generate-audio"),
    line_timings: str = Form(..., description="JSON list of {start, end, caption, speaker, emotion} from /jobs/generate-audio"),
    karaoke_captions: bool = Form(True),
):
    """
    Render the final video from already-generated audio + timings (ASYNC with
    progress tracking) - no TTS calls happen here.

    This is Phase 1 of the export endpoint: no overlay images/videos yet
    (that's added in Phase 2, into this same request). It exists to validate
    that the generate-audio -> preview -> export split works end-to-end.
    """
    try:
        timings = json.loads(line_timings)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid line_timings JSON")

    job_id = ProgressService.create_video_job(user_id=user_id, dialogue_title="Export")

    background_tasks.add_task(
        _process_export_job,
        job_id=job_id,
        user_id=user_id,
        video=video,
        audio_url=audio_url,
        timings=timings,
        karaoke_captions=karaoke_captions,
    )

    return {
        "job_id": job_id,
        "job_type": "video_generation",
        "message": "Export started. Connect to WebSocket for progress.",
        "websocket_url": f"/ws/progress/{job_id}",
        "status_url": f"/jobs/{job_id}/progress",
    }


async def _process_export_job(
    job_id: str,
    user_id: int,
    video: str,
    audio_url: str,
    timings: list,
    karaoke_captions: bool,
):
    """Background task: download the already-generated audio, composite with ffmpeg, upload."""
    session_id = uuid4().hex
    export_dir = DIRS["output"] / f"export_{session_id}"
    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        _validate_background_video()
        ProgressService.update_job(job_id=job_id, status="processing", current_stage="preparing_assets")

        background_path = await _run_blocking(_resolve_background_video, video)

        local_audio_path = export_dir / "narration.mp3"
        parsed_audio_url = urlparse(audio_url)
        if parsed_audio_url.scheme == "file":
            # Local storage backend - already on disk, no network round-trip
            local_audio_path.write_bytes(Path(parsed_audio_url.path).read_bytes())
        else:
            response = await _run_blocking(requests.get, audio_url, timeout=30)
            response.raise_for_status()
            local_audio_path.write_bytes(response.content)

        ProgressService.update_job(job_id=job_id, current_stage="video_assembly")

        video_output = export_dir / "final_video.mp4"
        caption_mode = "karaoke" if karaoke_captions else "box"
        video_path = await _run_blocking(
            create_video_with_audio_and_captions,
            background_video=str(background_path),
            audio_file=str(local_audio_path),
            caption_timings=timings,
            output_file=str(video_output),
            educational_images=None,  # Phase 2 adds overlays here
            caption_mode=caption_mode,
        )

        ProgressService.update_job(job_id=job_id, current_stage="uploading")

        collection_id = create_collection(user_id, "Export")
        video_service = VideoService()
        with open(video_path, "rb") as video_file:
            result = video_service.save_video(
                user_id=user_id,
                file_obj=video_file,
                original_filename="final_video.mp4",
                title="Exported Video",
                description="Exported without overlays (Phase 1)",
                collection_id=collection_id,
            )

        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={
                "collection_id": collection_id,
                "video_id": result["video_id"],
                "access_url": result["access_url"],
                "storage_key": result["storage_key"],
            },
        )

    except Exception as e:
        import traceback
        print(f"❌ EXPORT ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(e).__name__}: {str(e)}",
        )

    finally:
        shutil.rmtree(export_dir, ignore_errors=True)


# ============ Generate Audio from Dialogue

audioService = AudioService()

class AudioRequest(BaseModel):
    dialogue: str
    speaker: str

class BatchAudioRequest(BaseModel):
    lines: list[AudioRequest]

@app.post('/job/process_dialouge')
async def create_audio_from_dialouge(req: AudioRequest):

    return audioService.create_and_upload_audio(req.dialogue, req.speaker)

@app.post('/batch/process_dialouges')
async def batch_process_dialouge_generation(batch_request: BatchAudioRequest):
    dialouge_batch = []
    for request_payload in batch_request.lines:
        line = {}
        line.update(request_payload.model_dump())
        res = audioService.create_and_upload_audio(request_payload.dialogue, request_payload.speaker)
        line.update(res)
        dialouge_batch.append(line)

    return dialouge_batch


# ============ Helper Functions ============

def _resolve_background_video(video: Optional[str]) -> Path:
    """Download the selected background video from R2 for FFmpeg."""
    return get_background_video_from_storage(video)


def _validate_background_video():
    """Validate that background videos are available in the configured R2 location."""
    storage = get_storage_backend()
    prefix = getattr(storage, "background_prefix", "")
    if any(key.lower().endswith(".mp4") for key in storage.iter_keys(prefix)):
        return

    location = f" under '{prefix}'" if prefix else " at the bucket root"
    raise HTTPException(
        status_code=500,
        detail=f"No background videos found in R2{location}",
    )


def _move_upload_to_disk(upload: UploadFile, destination: Path):
    with destination.open("wb") as buffer:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)
    upload.file.close()


# ============ Image Upload Utilities ============

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


def _validate_image_files(images: List[UploadFile]):
    """Validate uploaded image files for format and size."""
    for image in images:
        if not image.filename:
            raise HTTPException(status_code=400, detail="Image filename missing")
        
        # Check extension
        ext = Path(image.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported image format: {ext}. Allowed: PNG, JPG, GIF"
            )
        
        # Check file size
        image.file.seek(0, 2)
        size = image.file.tell()
        image.file.seek(0)
        
        if size > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large: {image.filename} ({size/1024/1024:.1f}MB). Max: 10MB"
            )


def _save_uploaded_images(images: List[UploadFile], session_id: str) -> Path:
    """
    Save uploaded images to temporary directory.
    
    Returns:
        Path to session's image directory
    """
    session_dir = DIRS["temp_images"] / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    for image in images:
        if image.filename:
            dest = session_dir / image.filename
            _move_upload_to_disk(image, dest)
    
    return session_dir


def _validate_image_references(transcript_data: dict, image_dir: Path):
    """
    Validate that all image filenames in transcript exist in image_dir.

    Supports both:
    - New single dialogue format: { dialogue: { title, dialogue[] } } or { dialogue_data: { ... } }
    - Legacy multi-subtopic format: { subtopic_transcripts: [...] }

    Raises HTTPException if any referenced image not found.
    """
    referenced_images = set()

    # Support new single dialogue format (check both 'dialogue' and 'dialogue_data' keys)
    dialogue_data = transcript_data.get("dialogue") or transcript_data.get("dialogue_data")
    if dialogue_data and "dialogue" in dialogue_data:
        dialogue_lines = dialogue_data.get("dialogue") or []
        print(f"🔍 Checking for image references in {len(dialogue_lines)} dialogue lines...")
        for i, line in enumerate(dialogue_lines):
            # Check single image (legacy format)
            if line.get("image"):
                filename = line["image"].get("filename")
                if filename:
                    referenced_images.add(filename)
                    print(f"  📷 Found image reference at line {i}: {filename}")
            # Check images array (new multi-image format)
            if line.get("images") and isinstance(line["images"], list):
                for img in line["images"]:
                    filename = img.get("filename") if isinstance(img, dict) else None
                    if filename:
                        referenced_images.add(filename)
                        print(f"  📷 Found image reference at line {i}: {filename}")
    
    # Legacy: support old multi-subtopic format for backward compatibility
    for subtopic in transcript_data.get("subtopic_transcripts", []):
        for line in subtopic.get("dialogue", []):
            if line.get("image"):
                filename = line["image"]["filename"]
                referenced_images.add(filename)
    
    if not referenced_images:
        print("ℹ️  No image references found in transcript")
        return  # No images referenced, nothing to validate
    
    print(f"📋 Total referenced images: {referenced_images}")
    
    missing = []
    for filename in referenced_images:
        image_path = image_dir / filename
        if not image_path.exists():
            missing.append(filename)
            print(f"  ❌ Missing: {filename}")
        else:
            print(f"  ✅ Found: {filename} ({image_path})")
    
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Referenced images not found in upload: {', '.join(missing)}"
        )
    
    print(f"✅ All {len(referenced_images)} referenced images validated successfully")


def _extract_subtopic_number(video: dict) -> int:
    """Extract subtopic number from video title or description, otherwise return a high number."""
    # Check description first for "Subtopic X/Y" pattern
    description = video.get('description', '')
    if description:
        match = re.search(r'Subtopic\s*(\d+)/\d+', description, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    # Check title for patterns like "subtopic_1", "subtopic 1", or numbers
    title = video.get('title', '')
    if title:
        match = re.search(r'subtopic[_\s]?(\d+)', title, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    # If no explicit subtopic, return a high number to sort to the end
    return 999999


@app.get("/videos")
async def list_user_videos(
    collection_offset: int = Query(0, ge=0, description="Number of collections to skip"),
    collection_limit: int = Query(1, ge=1, le=10, description="Number of collections to return"),
    user_id: int = Depends(get_current_user_id),
):
    """
    Return videos grouped by collection for the current user.
    Fetches complete collections at a time (not breaking them up).
    
    Query params:
    - collection_offset: How many collections to skip (default 0)
    - collection_limit: How many collections to return (default 1, max 10)
    
    Returns collections in order (newest first), with videos within each collection sorted by subtopic (1→n).
    """
    try:
        # Step 1: Get the paginated collections (this is efficient - only metadata)
        collections = await _run_blocking(
            get_user_collections,
            user_id,
            collection_offset,
            collection_limit,
        )
        
        # Get total count of collections for pagination info
        all_collections = await _run_blocking(
            get_user_collections,
            user_id,
            0,
            1000,  # High limit to get count
        )
        total_collections = len(all_collections)
        
        # Step 2: Fetch videos ONLY for these specific collections
        result_videos = []
        for collection in collections:
            coll_id = collection["id"]
            
            # Fetch videos for this specific collection
            collection_videos = await _run_blocking(
                get_collection_videos,
                coll_id,
                0,
                50,
            )
            
            # Videos are already sorted by subtopic in get_collection_videos
            result_videos.extend(collection_videos)
        
        # Sanitize videos (remove internal fields)
        sanitized_videos = [
            {k: v for k, v in video.items() if k not in ["s3_key", "created_at", "user_id"]}
            for video in result_videos
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "collection_offset": collection_offset,
        "collection_limit": collection_limit,
        "total_collections": total_collections,
        "returned_video_count": len(sanitized_videos),
        "videos": sanitized_videos,
    }


# ============ Collection Endpoints ============

@app.get("/collections")
async def list_user_collections(
    start: int = Query(0, ge=0, description="Offset into collections list"),
    limit: int = Query(10, ge=1, le=50, description="Number of collections to return"),
    user_id: int = Depends(get_current_user_id),
):
    """
    List all collections for the current user.
    Returns ONLY: id and collection_title for each collection.
    """
    try:
        raw_collections = await _run_blocking(
            get_user_collections,
            user_id,
            start,
            limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    collections = [
        {
            "id": c["id"],
            "title": c["collection_title"],
        }
        for c in raw_collections
    ]

    return {
        "collections": collections,
    }


@app.get("/collections/{collection_id}")
async def get_collection_details(
    collection_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """
    Get a specific collection with all its videos.
    Videos are ordered by subtopic number (1→n).
    """
    try:
        # Get collection metadata
        collection = await _run_blocking(get_collection, collection_id)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")

        # Verify ownership
        if collection["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this collection")

        # Get all videos in the collection
        videos = await _run_blocking(get_collection_videos, collection_id)

        # Strip out any internal-only fields like s3_key
        sanitized_videos = [
            {k: v for k, v in video.items() if k != "s3_key" and k != "collection_id"}
            for video in videos
        ]

        return {
            "id": collection["id"],
            "title": collection["collection_title"],
            "video_count": len(sanitized_videos),
            "videos": sanitized_videos,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/videos/urls")
async def get_video_urls():
    try:
        storage = get_storage_backend()
        urls = storage.generate_background_urls()
        return {"videos": urls}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
