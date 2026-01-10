import asyncio
import random
import re
from pathlib import Path
from typing import List
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Query

from save_to_db.save_video import get_user_videos, get_collection_videos
from save_to_db.collection_service import get_collection, get_user_collections, find_last_collection
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from frontend_pipeline.script_generation.transcripts import extract_transcripts, extract_quiz_transcripts
from backend_pipeline.generate_subtopic_videos import (
    generate_videos_from_subtopic_list,
)
from backend_pipeline.generate_quiz_video import generate_quiz_video
import save_to_db.account_service as account_service

BACKGROUND_VIDEOS_DIR = Path("assets/videos")
OUTPUT_DIR = Path("assets/output")
TEMP_UPLOAD_DIR = Path("tmp/uploads")
GENERATED_AUDIO_DIR = Path("assets/audio/generated")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class DialogueLine(BaseModel):
    caption: str
    speaker: str


class SubtopicPayload(BaseModel):
    subtopic_title: str
    dialogue: List[DialogueLine]


class SubtopicRequest(BaseModel):
    subtopic_transcripts: List[SubtopicPayload]


class QuizScript(BaseModel):
    ask: str
    reveal: str


class QuizQuestion(BaseModel):
    question_number: int
    type: str
    question_text: str
    options: List[str]
    correct_answer: str
    script: QuizScript


class QuizModule(BaseModel):
    subtopic_title: str
    questions: List[QuizQuestion]


class QuizRequest(BaseModel):
    user_id: int
    quiz_modules: List[QuizModule]


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


def _is_youtube_url(text: str) -> bool:
    """Check if a string is a YouTube URL."""
    if not text:
        return False
    youtube_patterns = [
        r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/',
        r'youtube\.com/watch\?v=',
        r'youtu\.be/',
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in youtube_patterns)


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

async def _generate_quiz_videos(user_id, quiz_modules, prefix: str):
    session_id = uuid4().hex
    video_output_dir = OUTPUT_DIR / f"{prefix}_{session_id}"
    audio_output_dir = GENERATED_AUDIO_DIR / f"{prefix}_{session_id}"
    
    # Pass the videos directory so each subtopic can randomly select its own background
    return await _run_blocking(
        generate_quiz_video,
        quiz_modules,
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
    input_type: str = Form("auto", description="audio|text|youtube|auto (auto-detects from content)"),
    user_id: int = Form(1, description="User ID for video ownership"),
    content: str | None = Form(
        None,
        description="Text, YouTube URL, or other string content depending on input_type",
    ),
    file: UploadFile | None = File(
        None,
        description="Used when input_type is audio (MP3 upload).",
    ),
):
    input_type = input_type.lower()
    supported = {"audio", "text", "youtube", "auto"}
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
            elif content and _is_youtube_url(content):
                input_type = "youtube"
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
        elif input_type == "youtube":
            if not content:
                raise HTTPException(status_code=400, detail="YouTube URL is required in content field.")
            transcript_source = content
            transcript_type = "youtube"

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

        # Generate quiz modules (wrap in _run_blocking since it's synchronous)
        quiz_modules = await _run_blocking(
            extract_quiz_transcripts,
            transcript_source,
            transcript_type,
        )

        if not quiz_modules:
            detail = {
                "error": "model_returned_no_quiz_modules",
                "input_type": input_type,
                "content_preview": (transcript_source or "")[:280],
            }
            raise HTTPException(status_code=502, detail=detail)
        
        quiz_results = await _generate_quiz_videos(
            user_id,
            [quiz_module.model_dump() for quiz_module in quiz_modules],
            prefix="quiz_session",
        )

        # Get the last collection ID (wrap in _run_blocking)
        collection_dict = await _run_blocking(find_last_collection, user_id)
        collection_id = collection_dict["id"] if collection_dict else None

        return {
            "count": len(video_results),
            "results": video_results,
            "quiz_video": quiz_results,
            "collection_id": collection_id,
        }
    finally:
        if temp_audio_path and temp_audio_path.exists():
            temp_audio_path.unlink()




def get_current_user_id() -> int:
    # TODO: replace with your real auth
    return 1


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