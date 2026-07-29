import asyncio
import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, Depends, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from services.editor_audio_service import EditorAudioService
from services.media_service import (
    MAX_UPLOAD_BYTES,
    DEFAULT_CLIP_DURATION_MS,
    MediaAssetService,
    MediaValidationError,
)
from services.video_service import VideoService, get_collection_videos
from services.collection_service import create_collection, get_collection, get_user_collections, find_last_collection
from services.progress_service import ProgressService, set_event_loop
from services.repositories.editor_repository import (
    EditorClipValidationError,
    EditorCompositionRequiredError,
    EditorInvalidOrderError,
    EditorLineGeneratingError,
    EditorProjectNotFoundError,
    EditorRepository,
    EditorRevisionConflictError,
    MediaAssetInUseError,
    MediaAssetLimitError,
)
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_video import get_background_video_from_storage
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

# Where browsers can reach this API (used for dev asset content URLs).
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")

# ============ Pydantic Models ============

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


class EditorNarrationRestore(BaseModel):
    expected_project_revision: int


class EditorLineOrderUpdate(BaseModel):
    line_ids: List[UUID]
    expected_project_revision: int


class EditorVideoGenerateRequest(BaseModel):
    karaoke_captions: bool = True


class TimelineClipCreate(BaseModel):
    asset_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    x: float = Field(default=0.25, ge=0, le=1)
    y: float = Field(default=0.25, ge=0, le=1)
    width: float = Field(default=0.5, gt=0, le=1)
    z_index: int = Field(default=0, ge=-1000, le=1000)
    expected_project_revision: int


class TimelineClipUpdate(BaseModel):
    asset_id: Optional[UUID] = None
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, gt=0)
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, gt=0, le=1)
    z_index: Optional[int] = Field(default=None, ge=-1000, le=1000)
    expected_revision: int = Field(ge=1)


class TimelineClipDelete(BaseModel):
    expected_project_revision: int

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


@app.middleware("http")
async def reject_oversized_media_uploads(request: Request, call_next):
    """Reject obviously oversized multipart uploads before Starlette parses them.

    The extra 1 MiB allows multipart headers/boundaries while keeping a lying
    or absent Content-Length covered by the endpoint's capped read.
    """
    if request.method == "POST" and re.fullmatch(
        r"/editor/projects/[^/]+/assets", request.url.path
    ):
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > MAX_UPLOAD_BYTES + 1024 * 1024:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Image exceeds the maximum size of 10 MB"},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
    return await call_next(request)


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


def _asset_access_url(storage, asset: dict, project_id: Optional[UUID] = None) -> str:
    """Browser URL for an overlay asset through the authenticated API.

    The proxied MVP deliberately avoids requiring browser-facing R2 CORS and
    keeps local/R2 preview behavior identical. Export still reads storage keys.
    """
    owner_project_id = asset.get("project_id") or project_id
    return (
        f"{PUBLIC_API_BASE_URL}/editor/projects/{owner_project_id}"
        f"/assets/{asset['id']}/content"
    )


def _editor_project_response(project: dict) -> dict:
    """Attach fresh artifact URLs and timeline data to a repository project."""
    storage = get_storage_backend()
    result = dict(project)
    manifest = result.pop("active_composition_line_manifest", None) or []
    composition_key = result.pop("active_composition_storage_key", None)
    duration_ms = result.pop("active_composition_duration_ms", None)
    result["active_composition"] = None
    if composition_key and result.get("active_composition_id"):
        line_by_id = {str(line["id"]): line for line in result.get("dialogue", [])}
        words = []
        line_timings = []
        for index, entry in enumerate(manifest):
            start = entry["start_ms"] / 1000
            end = entry["end_ms"] / 1000
            line_id = str(entry["line_id"])
            line_timings.append({
                "index": index,
                "line_id": line_id,
                "start": start,
                "end": end,
                "duration": end - start,
                "caption": entry.get("caption", ""),
                "speaker": entry.get("speaker", "PETER"),
                "emotion": entry.get("emotion") or "neutral",
            })
            line = line_by_id.get(line_id, {})
            for word in line.get("active_segment_word_timings") or []:
                words.append({
                    "word": word["word"],
                    "start": start + word["start"],
                    "end": start + word["end"],
                    "line_index": index,
                    "line_id": line_id,
                })
        result["active_composition"] = {
            "id": str(result["active_composition_id"]),
            "audio_url": storage.generate_url(composition_key),
            "duration_ms": duration_ms,
            "line_timings": line_timings,
            "word_timestamps": words,
        }
    for video in result.get("exports", []):
        video["access_url"] = storage.generate_url(video["storage_key"])
    # Overlay asset URLs are minted fresh at read time, never persisted.
    assets = result.get("media_assets") or []
    for asset in assets:
        asset["access_url"] = _asset_access_url(storage, asset, result.get("id"))
    result["media_assets"] = assets
    result["timeline_clips"] = result.get("timeline_clips") or []
    return result


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
    return {"project": _editor_project_response(project)}


@app.post("/editor/projects/{project_id}/audio", status_code=202)
async def generate_editor_project_audio(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
):
    project = await _run_blocking(editor_repository.get_project, project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Editor project not found")
    job_id = ProgressService.create_audio_job(
        user_id=user_id, dialogue_title=str(project["title"])
    )
    background_tasks.add_task(
        _process_project_audio_job,
        job_id=job_id,
        project_id=project_id,
        user_id=user_id,
    )
    return {
        "job_id": job_id,
        "job_type": "audio_generation",
        "message": "Narration generation started.",
        "websocket_url": f"/ws/progress/{job_id}",
        "status_url": f"/jobs/{job_id}/progress",
    }


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
        return {"project": _editor_project_response(project)}
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
        return {"project": _editor_project_response(project)}
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
        return {"project": _editor_project_response(project)}
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
        return {"project": _editor_project_response(project)}
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


@app.post("/editor/projects/{project_id}/restore-narrated-script")
async def restore_narrated_script(
    project_id: UUID,
    payload: EditorNarrationRestore,
    user_id: int = Depends(get_current_user_id),
):
    """Restore text/speaker/emotion from the latest successful narration.

    Structural script edits are deliberately excluded from this first version.
    Visual media and timeline clips are never modified by this operation.
    """
    try:
        project = await _run_blocking(
            editor_repository.restore_narrated_script,
            project_id,
            user_id,
            payload.expected_project_revision,
        )
        return {"project": _editor_project_response(project)}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        EditorRevisionConflictError,
        EditorCompositionRequiredError,
        EditorInvalidOrderError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ============ Media Asset & Timeline Clip Endpoints ============


@app.post("/editor/projects/{project_id}/assets", status_code=201)
async def upload_editor_asset(
    project_id: UUID,
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """Proxied multipart image upload. Creates the asset only (no clip).

    The image is validated (PNG/JPEG/WebP, <=10MB, <=4096x4096), normalized
    to a single WebP with EXIF orientation applied and metadata discarded,
    and stored under a server-generated key. The original is not retained.
    """
    project = await _run_blocking(editor_repository.get_project, project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Editor project not found")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds the maximum size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    service = MediaAssetService(repository=editor_repository)
    try:
        asset = await _run_blocking(
            service.upload_image,
            project_id,
            user_id,
            data,
            file.filename or "image",
            file.content_type,
        )
    except (MediaValidationError, MediaAssetLimitError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    asset = dict(asset)
    asset["access_url"] = _asset_access_url(service.storage, asset, project_id)
    return {"asset": asset}


@app.get("/editor/projects/{project_id}/assets/{asset_id}/content")
async def get_editor_asset_content(
    project_id: UUID,
    asset_id: UUID,
    user_id: int = Depends(get_current_user_id),
):
    """Stream asset bytes through the API (dev parity for local storage)."""
    try:
        asset = await _run_blocking(
            editor_repository.get_media_asset, project_id, asset_id, user_id
        )
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    storage = get_storage_backend()
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".webp")
    handle.close()
    try:
        await _run_blocking(storage.download, asset["storage_key"], handle.name)
    except FileNotFoundError as exc:
        os.remove(handle.name)
        raise HTTPException(status_code=404, detail="Asset object not found") from exc
    except Exception as exc:
        os.remove(handle.name)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(
        handle.name,
        media_type=asset["content_type"],
        background=BackgroundTask(os.remove, handle.name),
        # Assets are immutable once created (new upload => new key)
        headers={"Cache-Control": "private, max-age=3600, immutable"},
    )


@app.delete("/editor/projects/{project_id}/assets/{asset_id}")
async def delete_editor_asset(
    project_id: UUID,
    asset_id: UUID,
    user_id: int = Depends(get_current_user_id),
):
    """Delete an asset that no timeline clip references (409 otherwise)."""
    service = MediaAssetService(repository=editor_repository)
    try:
        await _run_blocking(service.delete_asset, project_id, asset_id, user_id)
        project = await _run_blocking(
            editor_repository.get_project, project_id, user_id
        )
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MediaAssetInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "referencing_clip_ids": exc.referencing_clip_ids,
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="Editor project not found")
    return {"project": _editor_project_response(project)}


@app.post("/editor/projects/{project_id}/clips", status_code=201)
async def add_timeline_clip(
    project_id: UUID,
    payload: TimelineClipCreate,
    user_id: int = Depends(get_current_user_id),
):
    """Place an asset on the timeline at the playhead.

    Defaults to a 3-second window when end_ms is omitted; the end is clamped
    to the active composition duration. Requires active narration. Bumps the
    project revision WITHOUT invalidating the composition.
    """
    end_ms = payload.end_ms
    if end_ms is None:
        end_ms = payload.start_ms + DEFAULT_CLIP_DURATION_MS
    try:
        project = await _run_blocking(
            editor_repository.create_timeline_clip,
            project_id,
            user_id,
            payload.asset_id,
            payload.start_ms,
            end_ms,
            payload.x,
            payload.y,
            payload.width,
            payload.z_index,
            payload.expected_project_revision,
        )
        return {"project": _editor_project_response(project)}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EditorRevisionConflictError, EditorCompositionRequiredError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EditorClipValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/editor/projects/{project_id}/clips/{clip_id}")
async def update_timeline_clip(
    project_id: UUID,
    clip_id: UUID,
    payload: TimelineClipUpdate,
    user_id: int = Depends(get_current_user_id),
):
    """Debounced autosave edit: clip-scoped revision only.

    Replacing asset_id preserves geometry/timing (only provided fields
    change). Never touches the project revision or active composition.
    """
    updates = payload.model_dump(
        exclude_unset=True, exclude={"expected_revision"}, exclude_none=True
    )
    if not updates:
        raise HTTPException(status_code=422, detail="No clip fields to update")
    try:
        clip = await _run_blocking(
            editor_repository.update_timeline_clip,
            project_id,
            clip_id,
            user_id,
            updates,
            payload.expected_revision,
        )
        return {"clip": clip}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (EditorRevisionConflictError, EditorCompositionRequiredError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EditorClipValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/editor/projects/{project_id}/clips/{clip_id}")
async def delete_timeline_clip(
    project_id: UUID,
    clip_id: UUID,
    payload: TimelineClipDelete,
    user_id: int = Depends(get_current_user_id),
):
    try:
        project = await _run_blocking(
            editor_repository.delete_timeline_clip,
            project_id,
            clip_id,
            user_id,
            payload.expected_project_revision,
        )
        return {"project": _editor_project_response(project)}
    except EditorProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EditorRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ============ Async Job Endpoints (with Progress Tracking) ============

async def _process_project_audio_job(
    job_id: str, project_id: UUID, user_id: int
):
    try:
        ProgressService.update_job(
            job_id=job_id, status="processing", current_stage="tts_generation"
        )
        service = EditorAudioService()
        result = await _run_blocking(service.generate_narration, project_id, user_id)
        result["audio_url"] = service.storage.generate_url(result["storage_key"])
        ProgressService.update_job(job_id=job_id, status="completed", result=result)
    except Exception as exc:
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )


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
    if not project["background_video_id"]:
        raise HTTPException(status_code=409, detail="Project has no background video")
    if not project["active_composition_id"]:
        raise HTTPException(
            status_code=409,
            detail="Regenerate narration before generating the video",
        )

    job_id = ProgressService.create_video_job(
        user_id=user_id,
        dialogue_title=str(project["title"]),
    )
    background_tasks.add_task(
        _process_project_video_job,
        job_id=job_id,
        project_id=project_id,
        user_id=user_id,
        project_snapshot=project,
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


async def _process_project_video_job(
    job_id: str,
    project_id: UUID,
    user_id: int,
    project_snapshot: dict,
    karaoke_captions: bool,
):
    """Render the immutable project snapshot accepted by the export request."""
    export_dir = DIRS["output"] / f"project_{project_id}_{uuid4().hex}"
    export_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Use the snapshot captured synchronously by the 202 endpoint. Edits made
        # after Export is clicked belong to the next export, never this job.
        project = project_snapshot
        if not project or not project["active_composition_id"]:
            raise ValueError("Regenerate narration before generating the video")
        composition_key = project["active_composition_storage_key"]
        manifest = project["active_composition_line_manifest"] or []
        if not composition_key or not manifest:
            raise ValueError("Active narration composition is incomplete")

        ProgressService.update_job(
            job_id=job_id, status="processing", current_stage="preparing_assets"
        )
        background_path = await _run_blocking(
            _resolve_background_video, project["background_video_id"]
        )
        audio_path = export_dir / "narration.mp3"
        storage = get_storage_backend()
        await _run_blocking(storage.download, composition_key, str(audio_path))

        # Snapshot overlay clips + assets from the same project read (torn
        # states are impossible) and fetch images by storage key - never by
        # presigned URL, which could expire mid-render.
        overlay_clips = []
        timeline_clips = project.get("timeline_clips") or []
        if timeline_clips:
            assets_by_id = {
                str(asset["id"]): asset
                for asset in project.get("media_assets") or []
            }
            downloaded_by_key: Dict[str, str] = {}
            for clip in timeline_clips:
                # Fully out-of-range clips survive regeneration for user review,
                # but do not participate in preview/export until retimed.
                if clip.get("timing_status") != "aligned":
                    continue
                asset = assets_by_id.get(str(clip["asset_id"]))
                if asset is None:
                    continue
                asset_key = asset["storage_key"]
                if asset_key not in downloaded_by_key:
                    local_image = export_dir / f"overlay_{len(downloaded_by_key)}.webp"
                    await _run_blocking(storage.download, asset_key, str(local_image))
                    downloaded_by_key[asset_key] = str(local_image)
                overlay_clips.append(
                    {
                        "path": downloaded_by_key[asset_key],
                        "x": float(clip["x"]),
                        "y": float(clip["y"]),
                        "width": float(clip["width"]),
                        "start": clip["start_ms"] / 1000,
                        "end": clip["end_ms"] / 1000,
                        "z_index": clip["z_index"],
                    }
                )

        timings = [
            {
                "line_id": str(entry["line_id"]),
                "start": entry["start_ms"] / 1000,
                "end": entry["end_ms"] / 1000,
                "duration": (entry["end_ms"] - entry["start_ms"]) / 1000,
                "caption": entry.get("caption", ""),
                "speaker": entry.get("speaker", "PETER"),
                "emotion": entry.get("emotion") or "neutral",
            }
            for entry in manifest
        ]
        ProgressService.update_job(job_id=job_id, current_stage="video_assembly")
        output_path = export_dir / "final_video.mp4"
        rendered = await _run_blocking(
            create_video_with_audio_and_captions,
            background_video=str(background_path),
            audio_file=str(audio_path),
            caption_timings=timings,
            output_file=str(output_path),
            educational_images=None,
            caption_mode="karaoke" if karaoke_captions else "box",
            overlay_clips=overlay_clips,
        )

        ProgressService.update_job(job_id=job_id, current_stage="uploading")
        video_service = VideoService()
        with open(rendered, "rb") as video_file:
            saved = await _run_blocking(
                video_service.save_video,
                user_id=user_id,
                editor_project_id=project_id,
                file_obj=video_file,
                original_filename="final_video.mp4",
                title=str(project["title"]),
                description="Generated from persistent editor project",
            )
        ProgressService.update_job(
            job_id=job_id,
            status="completed",
            result={
                "video_id": saved["video_id"],
                "access_url": saved["access_url"],
                "storage_key": saved["storage_key"],
            },
        )
    except Exception as exc:
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        shutil.rmtree(export_dir, ignore_errors=True)


# ============ Helper Functions ============

def _resolve_background_video(video: Optional[str]) -> Path:
    """Download the selected background video from R2 for FFmpeg."""
    return get_background_video_from_storage(video)


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
