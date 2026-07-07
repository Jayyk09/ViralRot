import asyncio
import json
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import Literal

from services.audio_service import AudioService
from services.video_service import VideoService, get_collection_videos
from services.collection_service import create_collection, get_collection, get_user_collections, find_last_collection
from services.progress_service import ProgressService, set_event_loop
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_video import (
    generate_video_from_dialogue,
    generate_audio_for_dialogue,
    get_background_video,
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


# ============ Async Job Endpoints (with Progress Tracking) ============

@app.post("/jobs/generate-transcript")
async def create_transcript_job(
    background_tasks: BackgroundTasks,
    source_type: str = Form(..., description="youtube|audio|text|pptx"),
    user_id: int = Form(1),
    content: str | None = Form(None, description="Text content or YouTube URL"),
    file: UploadFile | None = File(None, description="Audio or PPTX file"),
):
    """
    Generate transcript from source material (ASYNC with progress tracking).

    Returns job_id immediately. Connect to WebSocket for real-time progress.

    Workflow:
    1. POST to this endpoint with source material
    2. Connect to WebSocket: /ws/progress/{job_id}
    3. Receive progress updates (extracting_content -> generating_dialogue)
    4. On completion, result contains dialogue data as JSON

    Stages:
    - extracting_content: Parse source (YouTube/audio/PPTX)
    - generating_dialogue: Create dialogue with Gemini AI

    Result format on completion:
        { "dialogue_data": { "title": "...", "dialogue": [...] } }

    Returns:
        job_id: Use with /ws/progress/{job_id} for real-time updates
    """
    # Validate source type
    valid_types = {"youtube", "text"}
    if source_type.lower() not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Prepare source input
    temp_file_path = None
    transcript_source = None
    transcript_type = None
    
    try:
        if source_type == "text":
            if not content:
                raise HTTPException(status_code=400, detail="Content required for source_type='text'")
            transcript_source = content
            transcript_type = "text"
        elif source_type == "youtube":
            if not content:
                raise HTTPException(status_code=400, detail="YouTube URL required for source_type='youtube'")
            transcript_source = content
            transcript_type = "youtube"
        else:
            return
        
        # Create job immediately
        job_id = ProgressService.create_transcript_job(user_id=user_id)
        
        # Start async processing in background
        background_tasks.add_task(
            _process_transcript_job,
            job_id=job_id,
            user_id=user_id,
            transcript_source=transcript_source,
            transcript_type=transcript_type,
            source_type=source_type,
            temp_file_path=str(temp_file_path) if temp_file_path else None,
        )
        
        return {
            "job_id": job_id,
            "job_type": "transcript_generation",
            "message": "Transcript generation started. Connect to WebSocket for progress.",
            "websocket_url": f"/ws/progress/{job_id}",
            "status_url": f"/jobs/{job_id}/progress",
        }
    
    except HTTPException:
        # Clean up temp file if validation fails
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()
        raise


async def _process_transcript_job(
    job_id: str,
    user_id: int,
    transcript_source: str,
    transcript_type: str,
    source_type: str,
    temp_file_path: Optional[str],
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
            transcript_source,
            transcript_type,
        )
        
        if not dialogue or not dialogue.dialogue:
            ProgressService.update_job(
                job_id=job_id,
                status="failed",
                error="No dialogue generated from source content. The AI model returned empty results.",
            )
            return
        
        # Complete job with result
        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={
                "dialogue": dialogue.model_dump()
            },
        )
    
    except Exception as e:
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(e).__name__}: {str(e)}",
        )
    
    finally:
        # Cleanup temp file
        if temp_file_path:
            temp_path = Path(temp_file_path)
            if temp_path.exists():
                temp_path.unlink()


@app.post("/jobs/generate-video")
async def create_video_job(
    background_tasks: BackgroundTasks,
    user_id: int = Form(1),
    video: str = Form(True, description="Optional background video name"), 
    images: List[UploadFile] = File(default=[], description="Optional educational images"),
    transcript: str | None = Form(None, description="Optional: Modified transcript JSON with image references"),
    karaoke_captions: bool = Form(True, description="Use karaoke-style captions (word-by-word yellow highlighting). Default: ON"),
):
    """
    Generate video from transcript JSON (ASYNC with progress tracking).

    Returns job_id immediately. Connect to WebSocket for real-time progress.

    Workflow:
    1. POST to this endpoint with transcript JSON and optional images
    2. Connect to WebSocket: /ws/progress/{job_id}
    3. Receive progress updates for video generation
    4. Get final result with collection_id and video URL

    Args:
        transcript: JSON string with dialogue data (required).
                    Format: { "dialogue_data": { "title": "...", "dialogue": [...] } }

    Caption Modes:
    - karaoke_captions=true (default): Words highlight yellow one-by-one as spoken
    - karaoke_captions=false: Traditional white text in black boxes

    Stages:
    - preparing_assets: Process uploaded images
    - audio_generation: Create TTS audio with MiniMax
    - video_assembly: FFmpeg overlay with captions
    - uploading: Upload to S3

    Returns:
        job_id: Use with /ws/progress/{job_id} for real-time updates
    """
    image_dir = None
    
    try:
        if transcript:
            transcript_data = json.loads(transcript)
        else:
            raise HTTPException(status_code=400, detail="No transcript provided")
            
        session_id = uuid4().hex
        image_dir = None
        
        # Debug logging for image uploads
        print(f"\n{'='*50}")
        print(f"🖼️  IMAGE UPLOAD DEBUG")
        print(f"{'='*50}")
        print(f"  images param: {images}")
        print(f"  images length: {len(images) if images else 0}")
        if images and len(images) > 0:
            print(f"  first image filename: {images[0].filename if images[0].filename else 'EMPTY'}")
            for i, img in enumerate(images):
                print(f"  image[{i}]: filename={img.filename}, content_type={img.content_type}")
        
        if images and len(images) > 0 and images[0].filename:
            print(f"✅ Processing {len(images)} uploaded images...")
            _validate_image_files(images)
            image_dir = _save_uploaded_images(images, session_id)
            print(f"💾 Saved images to: {image_dir}")
            _validate_image_references(transcript_data, image_dir)
        else:
            print(f"⚠️  No images to process (images={images}, len={len(images) if images else 0})")
        print(f"{'='*50}\n")
        
        # Get dialogue info (new single dialogue format)
        # Support both "dialogue" (new) and "dialogue_data" (legacy) keys
        dialogue_data = transcript_data.get("dialogue") or transcript_data.get("dialogue_data")
        if not dialogue_data:
            raise HTTPException(
                status_code=400,
                detail="Transcript contains no dialogue data"
            )
        
        dialogue_title = dialogue_data.get("title", "Untitled Dialogue")
        
        # Create job
        job_id = ProgressService.create_video_job(
            user_id=user_id,
            dialogue_title=dialogue_title,
        )
        
        # Start async processing
        background_tasks.add_task(
            _process_video_job,
            job_id=job_id,
            user_id=user_id,
            video=video,
            transcript_data=transcript_data,
            image_dir=str(image_dir) if image_dir else None,
            session_id=session_id,
            karaoke_captions=karaoke_captions,
        )
        
        return {
            "job_id": job_id,
            "job_type": "video_generation",
            "dialogue_title": dialogue_title,
            "karaoke_captions": karaoke_captions,
            "message": "Video generation started. Connect to WebSocket for progress.",
            "websocket_url": f"/ws/progress/{job_id}",
            "status_url": f"/jobs/{job_id}/progress",
        }
    
    except HTTPException:
        # Clean up image dir if validation fails
        if image_dir and image_dir.exists():
            shutil.rmtree(image_dir, ignore_errors=True)
        raise


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
        background_path = await _run_blocking(get_background_video, DIRS["background_videos"], video)

        ProgressService.update_job(job_id=job_id, current_stage="uploading")

        storage = get_storage_backend()
        if storage.backend_name.startswith("Local"):
            # Local backend never uploads backgrounds into its own storage
            # dir - they're read straight from DIRS["background_videos"] -
            # so presigning a "backgrounds/" key would point at a file that
            # doesn't exist. Serve the real path directly instead.
            background_video_url = f"file://{background_path.absolute()}"
        else:
            background_video_url = storage.generate_url(f"backgrounds/{background_path.name}")

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

        background_path = await _run_blocking(get_background_video, DIRS["background_videos"], video)

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

def _validate_background_video():
    """Validate that the background videos directory exists and has videos."""
    if not DIRS["background_videos"].exists():
        raise HTTPException(
            status_code=500,
            detail=f"Background videos directory not found at {DIRS['background_videos']}",
        )
    
    video_files = list(DIRS["background_videos"].glob("*.mp4"))
    if not video_files:
        raise HTTPException(
            status_code=500,
            detail=f"No background videos found in {DIRS["background_videos"]}",
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
