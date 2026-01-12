import asyncio
import json
import random
import re
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query
from typing import Literal

from save_to_db.save_video import get_user_videos, get_collection_videos
from save_to_db.collection_service import get_collection, get_user_collections, find_last_collection
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_subtopic_videos import (
    generate_videos_from_subtopic_list,
)
import save_to_db.account_service as account_service

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


class SubtopicPayload(BaseModel):
    subtopic_title: str
    dialogue: List[DialogueLine]


class SubtopicRequest(BaseModel):
    subtopic_transcripts: List[SubtopicPayload]


app = FastAPI(
    title="Video Generation API",
    description="API for generating videos from slides",
    version="1.0.0"
)

# CORS settings so React (localhost:3000) can talk to this API
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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


async def _run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def get_current_user_id() -> int:
    # TODO: replace with your real auth
    return 1


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


def _is_json_transcript(text: str) -> bool:
    """Check if a string looks like JSON transcript data."""
    if not text:
        return False
    text = text.strip()
    # Check if it starts with { or [ (JSON object or array)
    if text.startswith('{') or text.startswith('['):
        try:
            json.loads(text)
            return True
        except json.JSONDecodeError:
            return False
    return False


async def _generate_videos(user_id, subtopics, prefix: str):
    session_id = uuid4().hex
    video_output_dir = OUTPUT_DIR / f"{prefix}_{session_id}"
    audio_output_dir = GENERATED_AUDIO_DIR / f"{prefix}_{session_id}"
    
    # Pass the videos directory so each subtopic can randomly select its own background
    return await _run_blocking(
        generate_videos_from_subtopic_list,
        subtopics,
        str(BACKGROUND_VIDEOS_DIR),
        str(video_output_dir),
        str(audio_output_dir),
        user_id,
    )



async def generate_video_from_subtopics(payload: SubtopicRequest, user_id: int = 1):
    _validate_background_video()

    if not payload.subtopic_transcripts:
        raise HTTPException(status_code=400, detail="subtopic_transcripts cannot be empty.")

    session_id = uuid4().hex
    video_results = await _generate_videos(
        user_id,
        [subtopic.model_dump() for subtopic in payload.subtopic_transcripts],
        prefix="direct",
    )

    return {
        "count": len(video_results),
        "results": video_results,
    }

@app.post("/generate-video")
async def generate_video(
    input_type: str = Form("auto", description="audio|text|transcript|auto (auto-detects from content)"),
    user_id: int = Form(1, description="User ID for video ownership"),
    content: str | None = Form(
        None,
        description="Text content or pre-formatted JSON transcript",
    ),
    file: UploadFile | None = File(
        None,
        description="Used when input_type is audio (MP3 upload).",
    ),
):
    """
    Generate videos from various input types.

    Input types:
    - audio: MP3 file upload, processed by Gemini to generate dialogue
    - text: Raw text content, processed by Gemini to generate dialogue
    - transcript: Pre-formatted JSON matching the schema (bypasses Gemini)
    - auto: Automatically detect from content (JSON -> transcript, otherwise -> text)
    """
    input_type = input_type.lower()
    supported = {"audio", "text", "transcript", "auto"}
    if input_type not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"input_type must be one of {', '.join(sorted(supported))}",
        )

    temp_audio_path = None
    transcript_source = None
    transcript_type = None

    try:
        # Auto-detect input type
        if input_type == "auto":
            if file:
                input_type = "audio"
            elif content and _is_json_transcript(content):
                input_type = "transcript"
            elif content:
                input_type = "text"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Unable to auto-detect input type. Please provide either a file or content."
                )

        if input_type == "audio":
            if not file:
                raise HTTPException(status_code=400, detail="Audio file is required.")
            suffix = Path(file.filename or "").suffix or ".mp3"
            temp_audio_path = TEMP_UPLOAD_DIR / f"{uuid4().hex}{suffix}"
            _move_upload_to_disk(file, temp_audio_path)
            transcript_source = str(temp_audio_path)
            transcript_type = "audio/mp3"
        elif input_type == "text":
            if not content:
                raise HTTPException(status_code=400, detail="content is required for text input_type.")
            transcript_source = content
            transcript_type = "text"
        elif input_type == "transcript":
            if not content:
                raise HTTPException(status_code=400, detail="JSON content is required for transcript input_type.")
            transcript_source = content
            transcript_type = "transcript"

        subtopics = await _run_blocking(
            extract_transcripts,
            transcript_source,
            transcript_type,
        )
        
        if not subtopics:
            detail = {
                "error": "model_returned_no_subtopics",
                "input_type": input_type,
                "content_preview": (transcript_source or "")[:280],
            }
            raise HTTPException(status_code=502, detail=detail)

        video_results = await _generate_videos(
            user_id,
            [subtopic.model_dump() for subtopic in subtopics],
            prefix="session",
        )

        # Get the last collection ID (wrap in _run_blocking)
        collection_dict = await _run_blocking(find_last_collection, user_id)
        collection_id = collection_dict["id"] if collection_dict else None

        return {
            "count": len(video_results),
            "results": video_results,
            "collection_id": collection_id,
        }
    finally:
        if temp_audio_path and temp_audio_path.exists():
            temp_audio_path.unlink()


# ============ Transcript Generation (for image workflow) ============

def _add_metadata_to_transcript(transcript_data: dict):
    """Add line numbers and duration estimates to transcript (in-place)."""
    for subtopic in transcript_data.get("subtopic_transcripts", []):
        for idx, line in enumerate(subtopic.get("dialogue", []), start=1):
            line["line_number"] = idx
            # Estimate duration: ~150 words/min = ~2.5 words/sec
            word_count = len(line["caption"].split())
            line["duration_estimate"] = round(word_count / 2.5, 1)


@app.post("/generate-transcript")
async def generate_transcript_endpoint(
    source_type: str = Form(..., description="youtube|audio|text|pptx"),
    user_id: int = Form(1),
    content: str | None = Form(None, description="Text content or YouTube URL"),
    file: UploadFile | None = File(None, description="Audio or PPTX file"),
):
    """
    Generate transcript only (no video generation).
    Saves transcript to memory for 24 hours.
    
    Use this when you want to:
    1. Review the generated dialogue before creating videos
    2. Add educational images to specific dialogue lines
    3. Modify the transcript before video generation
    
    Returns:
    - transcript_id: Use this ID with /generate-video-with-images
    - expires_in_hours: How long the transcript is stored (24h)
    - subtopic_transcripts: The generated dialogue with metadata
    """
    temp_file_path = None
    
    try:
        # Handle source input based on type
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
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported source_type: {source_type}. Use: youtube, audio, text, pptx"
            )
        
        # Generate transcript using existing pipeline
        subtopics = await _run_blocking(
            extract_transcripts,
            transcript_source,
            transcript_type,
        )
        
        if not subtopics:
            raise HTTPException(
                status_code=502,
                detail="No subtopics generated from the source content"
            )
        
        # Build transcript data with metadata
        transcript_data = {
            "subtopic_transcripts": [s.model_dump() for s in subtopics]
        }
        _add_metadata_to_transcript(transcript_data)
        
        # Save to memory
        transcript_id = save_transcript_memory(user_id, transcript_data, source_type)
        
        return {
            "transcript_id": transcript_id,
            "expires_in_hours": 24,
            "subtopic_count": len(transcript_data["subtopic_transcripts"]),
            "subtopic_transcripts": transcript_data["subtopic_transcripts"],
        }
    
    finally:
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink()


@app.get("/transcripts/{transcript_id}")
async def get_transcript_endpoint(
    transcript_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """
    Retrieve a saved transcript by ID.
    
    Transcripts are stored for 24 hours after generation.
    Only the user who generated the transcript can access it.
    """
    transcript = get_transcript_memory(transcript_id, user_id)
    
    if not transcript:
        raise HTTPException(
            status_code=404,
            detail="Transcript not found, expired, or access denied"
        )
    
    return {
        "transcript_id": transcript_id,
        "source_type": transcript["source_type"],
        "subtopic_transcripts": transcript["data"]["subtopic_transcripts"],
    }


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


@app.post("/generate-video-with-images")
async def generate_video_with_images(
    transcript_id: str = Form(..., description="Transcript ID from /generate-transcript"),
    user_id: int = Form(1),
    images: List[UploadFile] = File(default=[], description="Educational image files"),
    updated_transcript: str | None = Form(None, description="Optional: Updated transcript JSON with image references"),
):
    """
    Generate video from saved transcript with educational images.
    
    Workflow:
    1. Call /generate-transcript to get a transcript_id
    2. Review the transcript and add image references to dialogue lines
    3. Call this endpoint with:
       - transcript_id: The ID from step 1
       - images[]: Upload your image files
       - updated_transcript: JSON with image references added to dialogue lines
    
    Example updated_transcript format:
    {
      "subtopic_transcripts": [
        {
          "subtopic_title": "...",
          "dialogue": [
            {
              "caption": "...",
              "speaker": "PETER",
              "emotion": "neutral",
              "image": {
                "filename": "diagram.png",
                "size": "medium"
              }
            }
          ]
        }
      ]
    }
    """
    image_dir = None
    
    try:
        # 1. Retrieve saved transcript from memory
        saved_transcript = get_transcript_memory(transcript_id, user_id)
        
        if not saved_transcript:
            raise HTTPException(
                status_code=404,
                detail="Transcript not found, expired, or access denied"
            )
        
        # 2. Use updated transcript if provided, otherwise use saved
        if updated_transcript:
            try:
                transcript_data = json.loads(updated_transcript)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid transcript JSON format")
        else:
            transcript_data = saved_transcript["data"]
        
        # 3. Handle images if provided
        session_id = uuid4().hex
        if images and len(images) > 0 and images[0].filename:
            # Validate uploaded images
            _validate_image_files(images)
            
            # Save images temporarily
            image_dir = _save_uploaded_images(images, session_id)
            
            # Validate image references exist
            _validate_image_references(transcript_data, image_dir)
        
        # 4. Generate videos with images
        video_results = await _generate_videos_with_images(
            user_id=user_id,
            subtopics=transcript_data["subtopic_transcripts"],
            image_dir=str(image_dir) if image_dir else None,
            prefix="session",
        )
        
        # 5. Get collection ID
        collection_dict = await _run_blocking(find_last_collection, user_id)
        collection_id = collection_dict["id"] if collection_dict else None
        
        return {
            "collection_id": collection_id,
            "video_count": len(video_results),
            "results": video_results,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Cleanup temp images
        if image_dir and image_dir.exists():
            shutil.rmtree(image_dir, ignore_errors=True)


async def _generate_videos_with_images(user_id, subtopics, image_dir, prefix):
    """Generate videos with optional educational images."""
    session_id = uuid4().hex
    video_output_dir = OUTPUT_DIR / f"{prefix}_{session_id}"
    audio_output_dir = GENERATED_AUDIO_DIR / f"{prefix}_{session_id}"
    
    return await _run_blocking(
        generate_videos_from_subtopic_list,
        subtopics,
        str(BACKGROUND_VIDEOS_DIR),
        str(video_output_dir),
        str(audio_output_dir),
        user_id,
        None,  # collection_id
        image_dir,  # Pass image directory (can be None)
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