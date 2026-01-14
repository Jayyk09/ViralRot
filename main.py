import asyncio
import json
import random
import re
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import Literal

from services.video_service import VideoService, get_user_videos, get_collection_videos
from services.collection_service import get_collection, get_user_collections, find_last_collection
from services.progress_service import ProgressService, set_event_loop
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_video import (
    generate_video_from_dialogue,
)
import services.account_service as account_service

BACKGROUND_VIDEOS_DIR = Path("assets/videos")
OUTPUT_DIR = Path("assets/output")
TEMP_UPLOAD_DIR = Path("tmp/uploads")
TEMP_IMAGES_DIR = Path("tmp/uploads/images")
GENERATED_AUDIO_DIR = Path("assets/audio/generated")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ============ In-Memory Transcript Storage ============
# Structure: {transcript_id: {data, created_at, user_id}}
TRANSCRIPT_STORAGE: Dict[str, dict] = {}
TRANSCRIPT_LOCK = threading.Lock()
TRANSCRIPT_TTL = timedelta(hours=24)  # Expire after 24 hours


def save_transcript_memory(user_id: int, transcript_data: dict, source_type: str) -> str:
    """Save transcript to memory with expiration."""
    transcript_id = uuid4().hex
    
    with TRANSCRIPT_LOCK:
        TRANSCRIPT_STORAGE[transcript_id] = {
            "data": transcript_data,
            "user_id": user_id,
            "source_type": source_type,
            "created_at": datetime.now(),
        }
    
    return transcript_id


def get_transcript_memory(transcript_id: str, user_id: Optional[int] = None) -> Optional[dict]:
    """Retrieve transcript from memory with authorization check."""
    with TRANSCRIPT_LOCK:
        transcript = TRANSCRIPT_STORAGE.get(transcript_id)
        
        if not transcript:
            return None
        
        # Check expiration
        age = datetime.now() - transcript["created_at"]
        if age > TRANSCRIPT_TTL:
            del TRANSCRIPT_STORAGE[transcript_id]
            return None
        
        # Check authorization
        if user_id is not None and transcript["user_id"] != user_id:
            return None
        
        return transcript


def cleanup_expired_transcripts_memory() -> int:
    """Remove expired transcripts from memory."""
    now = datetime.now()
    with TRANSCRIPT_LOCK:
        expired = [
            tid for tid, t in TRANSCRIPT_STORAGE.items()
            if now - t["created_at"] > TRANSCRIPT_TTL
        ]
        for tid in expired:
            del TRANSCRIPT_STORAGE[tid]
    
    return len(expired)


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


# DEPRECATED: Kept for backward compatibility
class SubtopicPayload(BaseModel):
    """DEPRECATED: Use DialoguePayload instead."""
    subtopic_title: str
    dialogue: List[DialogueLine]


class SubtopicRequest(BaseModel):
    """DEPRECATED: Use VideoGenerationRequest instead."""
    subtopic_transcripts: List[SubtopicPayload]


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
    expired_transcripts = cleanup_expired_transcripts_memory()
    print(f"Shutdown cleanup: {expired_jobs} jobs, {expired_transcripts} transcripts removed")


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
            "frontend": ["OCR", "Script Generation"],
            "backend": ["Audio Generation", "Video Assembly"]
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# ============ WebSocket Progress Endpoint ============

def get_current_user_id() -> int:
    """Get current user ID. TODO: Replace with real auth."""
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
    When complete, result contains transcript_id for use with /jobs/generate-video.
    
    Workflow:
    1. POST to this endpoint with source material
    2. Connect to WebSocket: /ws/progress/{job_id}
    3. Receive progress updates (extracting_content → generating_dialogue)
    4. Get final result with transcript_id and transcript JSON
    
    Stages:
    - extracting_content: Parse source (YouTube/audio/PPTX)
    - generating_dialogue: Create dialogue with Gemini AI
    
    Returns:
        job_id: Use with /ws/progress/{job_id} for real-time updates
    """
    # Validate source type
    valid_types = {"youtube", "audio", "text", "pptx"}
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
        if source_type == "audio":
            if not file:
                raise HTTPException(status_code=400, detail="Audio file required for source_type='audio'")
            suffix = Path(file.filename or "").suffix or ".mp3"
            temp_file_path = TEMP_UPLOAD_DIR / f"{uuid4().hex}{suffix}"
            _move_upload_to_disk(file, temp_file_path)
            transcript_source = str(temp_file_path)
            transcript_type = "audio/mp3"
        elif source_type == "text":
            if not content:
                raise HTTPException(status_code=400, detail="Content required for source_type='text'")
            transcript_source = content
            transcript_type = "text"
        elif source_type == "youtube":
            if not content:
                raise HTTPException(status_code=400, detail="YouTube URL required for source_type='youtube'")
            transcript_source = content
            transcript_type = "youtube"
        elif source_type == "pptx":
            if not file:
                raise HTTPException(status_code=400, detail="PPTX file required for source_type='pptx'")
            temp_file_path = TEMP_UPLOAD_DIR / f"{uuid4().hex}.pptx"
            _move_upload_to_disk(file, temp_file_path)
            transcript_source = str(temp_file_path)
            transcript_type = "pptx"
        
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
        
        # Build transcript data with metadata
        transcript_data = {
            "dialogue_data": dialogue.model_dump()
        }
        _add_metadata_to_transcript(transcript_data)
        
        # Save to memory storage (reuse existing storage for transcript lookup)
        transcript_id = save_transcript_memory(user_id, transcript_data, source_type)
        
        # Complete job with result
        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={
                "transcript_id": transcript_id,
                "expires_in_hours": 24,
                "dialogue": transcript_data["dialogue_data"],
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
    transcript_id: str = Form(..., description="Transcript ID from /jobs/generate-transcript"),
    user_id: int = Form(1),
    images: List[UploadFile] = File(default=[], description="Optional educational images"),
    updated_transcript: str | None = Form(None, description="Optional: Modified transcript JSON with image references"),
    karaoke_captions: bool = Form(True, description="Use karaoke-style captions (word-by-word yellow highlighting). Default: ON"),
):
    """
    Generate videos from transcript (ASYNC with progress tracking).
    
    Returns job_id immediately. Connect to WebSocket for real-time progress.
    
    Workflow:
    1. Get transcript_id from /jobs/generate-transcript
    2. (Optional) Edit transcript and add image references
    3. POST to this endpoint with transcript_id, optional images, and updated transcript
    4. Connect to WebSocket: /ws/progress/{job_id}
    5. Receive progress updates for video generation
    6. Get final result with collection_id and video URL
    
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
        # Retrieve transcript from memory
        saved_transcript = get_transcript_memory(transcript_id, user_id)
        if not saved_transcript:
            raise HTTPException(
                status_code=404,
                detail="Transcript not found, expired (24h TTL), or access denied"
            )
        
        # Use updated transcript if provided, otherwise use saved
        if updated_transcript:
            try:
                transcript_data = json.loads(updated_transcript)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid transcript JSON format: {str(e)}"
                )
        else:
            transcript_data = saved_transcript["data"]
        
        # Handle optional images
        session_id = uuid4().hex
        image_dir = None
        if images and len(images) > 0 and images[0].filename:
            _validate_image_files(images)
            image_dir = _save_uploaded_images(images, session_id)
            _validate_image_references(transcript_data, image_dir)
        
        # Get dialogue info (new single dialogue format)
        dialogue_data = transcript_data.get("dialogue_data")
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
        
        # Extract dialogue data
        dialogue_data = transcript_data["dialogue_data"]
        
        # Generate single video with progress callback
        session_id_full = uuid4().hex
        video_output_dir = OUTPUT_DIR / f"job_{session_id_full}"
        audio_output_dir = GENERATED_AUDIO_DIR / f"job_{session_id_full}"
        
        # Progress callback wrapper for single video
        def progress_callback(job_id, current_stage, title):
            ProgressService.update_job(
                job_id=job_id,
                current_stage=current_stage,
            )
        
        video_result = await _run_blocking(
            generate_video_from_dialogue,
            dialogue_data,
            str(BACKGROUND_VIDEOS_DIR),
            str(video_output_dir),
            str(audio_output_dir),
            user_id,
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


# ============ Helper Functions ============

def _validate_background_video():
    """Validate that the background videos directory exists and has videos."""
    if not BACKGROUND_VIDEOS_DIR.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Background videos directory not found at {BACKGROUND_VIDEOS_DIR}",
        )
    
    video_files = list(BACKGROUND_VIDEOS_DIR.glob("*.mp4"))
    if not video_files:
        raise HTTPException(
            status_code=500,
            detail=f"No background videos found in {BACKGROUND_VIDEOS_DIR}",
        )


def _move_upload_to_disk(upload: UploadFile, destination: Path):
    with destination.open("wb") as buffer:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)
    upload.file.close()


# ============ Transcript Generation Helpers ============

def _add_metadata_to_transcript(transcript_data: dict):
    """Add line numbers and duration estimates to transcript (in-place)."""
    for subtopic in transcript_data.get("subtopic_transcripts", []):
        for idx, line in enumerate(subtopic.get("dialogue", []), start=1):
            line["line_number"] = idx
            # Estimate duration: ~150 words/min = ~2.5 words/sec
            word_count = len(line["caption"].split())
            line["duration_estimate"] = round(word_count / 2.5, 1)


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
    session_dir = TEMP_IMAGES_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    for image in images:
        if image.filename:
            dest = session_dir / image.filename
            _move_upload_to_disk(image, dest)
    
    return session_dir


def _validate_image_references(transcript_data: dict, image_dir: Path):
    """
    Validate that all image filenames in transcript exist in image_dir.
    
    Raises HTTPException if any referenced image not found.
    """
    referenced_images = set()
    
    for subtopic in transcript_data.get("subtopic_transcripts", []):
        for line in subtopic.get("dialogue", []):
            if line.get("image"):
                filename = line["image"]["filename"]
                referenced_images.add(filename)
    
    if not referenced_images:
        return  # No images referenced, nothing to validate
    
    missing = []
    for filename in referenced_images:
        if not (image_dir / filename).exists():
            missing.append(filename)
    
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Referenced images not found in upload: {', '.join(missing)}"
        )


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


# ============ Account CRUD Endpoints ============

class UserCreate(BaseModel):
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserUpdatePassword(BaseModel):
    new_password: str


@app.post("/accounts")
async def register_account(user: UserCreate):
    """Create a new user account."""
    result = await _run_blocking(account_service.create_user, user.email, user.password)
    if result is None:
        raise HTTPException(status_code=400, detail="Email already exists")
    return {"message": "Account created", "user": result}


@app.post("/accounts/login")
async def login_account(credentials: UserLogin):
    """Authenticate user and return user info."""
    result = await _run_blocking(account_service.authenticate_user, credentials.email, credentials.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful", "user": result}


@app.get("/accounts/{user_id}")
async def get_account(user_id: int):
    """Get user account by ID."""
    result = await _run_blocking(account_service.get_user_by_id, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    return result


@app.get("/accounts")
async def list_accounts():
    """List all user accounts."""
    users = await _run_blocking(account_service.list_all_users)
    return {"count": len(users), "users": users}
