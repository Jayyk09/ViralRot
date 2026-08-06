"""
Progress tracking service for async job management.

Provides in-memory storage for job progress and WebSocket broadcasting
for real-time updates to frontend clients.

Supports two job types:
- transcript_generation: Extract and generate dialogue from source
- video_generation: Create videos from transcript with TTS and FFmpeg
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Union
from uuid import uuid4
from pydantic import BaseModel, Field
import threading

from services.generation_errors import GenerationError

# Type definitions
JobType = Literal[
    "transcript_generation", "video_generation", "audio_generation", "visual_generation"
]
JobStatus = Literal[
    "queued", "processing", "awaiting_review", "completed", "failed", "cancelled"
]
TranscriptStage = Literal["extracting_content", "generating_dialogue"]
VideoStage = Literal["preparing_assets", "audio_generation", "video_assembly", "uploading"]
AudioStage = Literal["tts_generation", "concatenation", "uploading"]
VisualStage = Literal[
    "capturing_narration",
    "planning",
    "searching_images",
    "awaiting_review",
    "retrieving_images",
    "placing_visuals",
    "cancelling",
]
VisualSlotStatus = Literal[
    "planned",
    "searching",
    "awaiting_review",
    "retrieving",
    "ingested",
    "placed",
    "skipped_manual_overlap",
    "skipped_by_user",
    "failed",
]

# ============ Event Loop Storage ============
# Store reference to main event loop for thread-safe operations
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """
    Set the main event loop for thread-safe operations.
    
    This should be called once during application startup with the FastAPI event loop.
    It enables progress updates to be broadcast from background threads.
    
    Args:
        loop: The asyncio event loop to use for scheduling broadcasts
    """
    global _main_event_loop
    _main_event_loop = loop


# ============ Pydantic Models ============


class GenerationErrorPayload(BaseModel):
    """Stable, provider-independent failure information exposed to job clients."""

    code: str
    message: str
    retry_action: str


class VisualSlotView(BaseModel):
    """Client-safe view of one transient visual slot.

    Candidate dicts already exclude the original third-party URL (see
    ReviewImageCandidate.to_dict()); only an opaque, server-verified token
    authorizes a later placement selection.
    """

    slot_id: str
    start_line_id: str
    end_line_id: str
    start_ms: int
    end_ms: int
    query: str
    status: VisualSlotStatus
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    asset_id: Optional[str] = None
    error: Optional[GenerationErrorPayload] = None


class TranscriptJobProgress(BaseModel):
    """Progress state for transcript generation job."""
    job_id: str
    user_id: int
    job_type: Literal["transcript_generation"] = "transcript_generation"
    status: JobStatus = "queued"
    current_stage: TranscriptStage = "extracting_content"
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    generation_error: Optional[GenerationErrorPayload] = None
    result: Optional[dict] = None  # Contains transcript_id + transcript JSON
    
    @property
    def percentage(self) -> int:
        """Calculate progress percentage."""
        if self.status == "completed":
            return 100
        if self.status == "failed":
            return 0
        # Two stages: extracting (0-50%) and generating (50-100%)
        return 25 if self.current_stage == "extracting_content" else 60
    
    @property
    def message(self) -> str:
        """Human-readable progress message."""
        if self.status == "completed":
            return "Transcript generation complete!"
        if self.status == "failed":
            return f"Failed: {self.error}"
        if self.current_stage == "extracting_content":
            return "Extracting content from source..."
        return "Generating dialogue with AI..."


class VideoJobProgress(BaseModel):
    """Progress state for video generation job."""
    job_id: str
    user_id: int
    job_type: Literal["video_generation"] = "video_generation"
    status: JobStatus = "queued"
    current_stage: VideoStage = "preparing_assets"
    dialogue_title: Optional[str] = None  # Single video title
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    generation_error: Optional[GenerationErrorPayload] = None
    result: Optional[dict] = None  # Contains exported video information
    
    @property
    def percentage(self) -> int:
        """Calculate overall progress percentage."""
        if self.status == "completed":
            return 100
        if self.status == "failed":
            return 0
        
        # 4 stages total
        stage_order = ["preparing_assets", "audio_generation", "video_assembly", "uploading"]
        if self.current_stage in stage_order:
            stage_index = stage_order.index(self.current_stage)
            return min(99, int((stage_index / len(stage_order)) * 100))
        return 0
    
    @property
    def message(self) -> str:
        """Human-readable progress message."""
        if self.status == "completed":
            return "Video generated successfully!"
        if self.status == "failed":
            return f"Failed: {self.error}"
        
        stage_messages = {
            "preparing_assets": "Preparing assets...",
            "audio_generation": "Generating audio...",
            "video_assembly": "Assembling video...",
            "uploading": "Uploading to storage...",
        }
        stage_msg = stage_messages.get(self.current_stage, self.current_stage)
        
        if self.dialogue_title:
            return f"{stage_msg} ({self.dialogue_title})"
        return stage_msg


class AudioJobProgress(BaseModel):
    """Progress state for standalone audio generation job (TTS + timings, no rendering)."""
    job_id: str
    user_id: int
    job_type: Literal["audio_generation"] = "audio_generation"
    status: JobStatus = "queued"
    current_stage: AudioStage = "tts_generation"
    dialogue_title: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    generation_error: Optional[GenerationErrorPayload] = None
    result: Optional[dict] = None  # Contains audio_url, line_timings, word_timestamps, background_video_url

    @property
    def percentage(self) -> int:
        """Calculate progress percentage."""
        if self.status == "completed":
            return 100
        if self.status == "failed":
            return 0
        stage_order = ["tts_generation", "concatenation", "uploading"]
        if self.current_stage in stage_order:
            stage_index = stage_order.index(self.current_stage)
            return min(99, int((stage_index / len(stage_order)) * 100))
        return 0

    @property
    def message(self) -> str:
        """Human-readable progress message."""
        if self.status == "completed":
            return "Audio generated successfully!"
        if self.status == "failed":
            return f"Failed: {self.error}"

        stage_messages = {
            "tts_generation": "Generating speech audio...",
            "concatenation": "Combining audio segments...",
            "uploading": "Uploading audio...",
        }
        stage_msg = stage_messages.get(self.current_stage, self.current_stage)

        if self.dialogue_title:
            return f"{stage_msg} ({self.dialogue_title})"
        return stage_msg


class VisualJobProgress(BaseModel):
    """Progress state for a transient post-narration visual-generation run."""
    job_id: str
    user_id: int
    job_type: Literal["visual_generation"] = "visual_generation"
    status: JobStatus = "queued"
    mode: Literal["automatic", "review"] = "automatic"
    current_stage: VisualStage = "capturing_narration"
    project_id: str
    composition_id: Optional[str] = None
    dialogue_title: Optional[str] = None
    retry_of_job_id: Optional[str] = None
    slots: List[VisualSlotView] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    generation_error: Optional[GenerationErrorPayload] = None
    result: Optional[dict] = None

    @property
    def percentage(self) -> int:
        if self.status == "completed":
            return 100
        if self.status in ("failed", "cancelled"):
            return 0
        if not self.slots:
            stage_order = ["capturing_narration", "planning"]
            if self.current_stage in stage_order:
                return min(20, (stage_order.index(self.current_stage) + 1) * 10)
            return 5
        settled = sum(
            1
            for slot in self.slots
            if slot.status
            in ("placed", "failed", "skipped_manual_overlap", "skipped_by_user", "ingested")
        )
        return min(99, 20 + int((settled / len(self.slots)) * 79))

    @property
    def message(self) -> str:
        if self.status == "completed":
            return "Visual generation complete!"
        if self.status == "cancelled":
            return "Visual generation was cancelled."
        if self.status == "failed":
            return f"Failed: {self.error}"
        if self.status == "awaiting_review":
            return "Review the suggested visuals."
        stage_messages = {
            "capturing_narration": "Reading the finalized narration...",
            "planning": "Planning useful visuals...",
            "searching_images": "Finding images...",
            "retrieving_images": "Fetching images...",
            "placing_visuals": "Placing visuals on the timeline...",
            "cancelling": "Cancelling...",
        }
        base = stage_messages.get(self.current_stage, self.current_stage)
        if self.slots and self.current_stage in ("searching_images", "retrieving_images"):
            settled = sum(
                1
                for slot in self.slots
                if slot.status
                in ("placed", "failed", "skipped_manual_overlap", "skipped_by_user", "ingested")
            )
            return f"{base} · {settled}/{len(self.slots)}"
        return base


# DEPRECATED: Kept for backward compatibility
class SubtopicProgress(BaseModel):
    """DEPRECATED: Progress for a single subtopic in video generation."""
    index: int
    title: str
    stage: Literal["queued", "preparing_assets", "audio_generation", "video_assembly", "uploading", "completed", "failed"]
    error: Optional[str] = None


class ProgressUpdate(BaseModel):
    """WebSocket message format for progress updates."""
    type: Literal["progress", "completed", "error", "cancelled"]
    job_id: str
    job_type: JobType
    status: JobStatus
    percentage: int
    message: str
    current_stage: Optional[str] = None
    dialogue_title: Optional[str] = None  # For single dialogue video jobs
    # Visual-generation-specific fields (absent for other job types)
    mode: Optional[Literal["automatic", "review"]] = None
    project_id: Optional[str] = None
    composition_id: Optional[str] = None
    retry_of_job_id: Optional[str] = None
    slots: Optional[List[VisualSlotView]] = None
    # Deprecated fields (kept for backward compatibility)
    current_subtopic: Optional[int] = None
    total_subtopics: Optional[int] = None
    subtopic_title: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    generation_error: Optional[GenerationErrorPayload] = None


# Union type for storage
JobProgress = Union[
    TranscriptJobProgress, VideoJobProgress, AudioJobProgress, VisualJobProgress
]


# ============ In-Memory Storage ============

PROGRESS_STORAGE: Dict[str, JobProgress] = {}
WEBSOCKET_CONNECTIONS: Dict[str, Set] = {}  # job_id -> Set[WebSocket]
STORAGE_LOCK = threading.Lock()
PROGRESS_TTL = timedelta(hours=1)
_UNSET = object()


# ============ Progress Service ============

class ProgressService:
    """
    Service for managing job progress and WebSocket connections.
    
    Usage:
        # Create a new job
        job_id = ProgressService.create_transcript_job(user_id=1)
        
        # Update progress
        ProgressService.update_job(job_id, current_stage="generating_dialogue")
        
        # Complete job
        ProgressService.update_job(job_id, status="completed", result={...})
    """
    
    @staticmethod
    def create_transcript_job(user_id: int) -> str:
        """Create a new transcript generation job."""
        job_id = uuid4().hex
        
        job = TranscriptJobProgress(
            job_id=job_id,
            user_id=user_id,
            created_at=datetime.now(),
        )
        
        with STORAGE_LOCK:
            PROGRESS_STORAGE[job_id] = job
            WEBSOCKET_CONNECTIONS[job_id] = set()
        
        return job_id
    
    @staticmethod
    def create_video_job(user_id: int, dialogue_title: Optional[str] = None) -> str:
        """Create a new video generation job for single dialogue."""
        job_id = uuid4().hex
        
        job = VideoJobProgress(
            job_id=job_id,
            user_id=user_id,
            dialogue_title=dialogue_title,
            created_at=datetime.now(),
        )
        
        with STORAGE_LOCK:
            PROGRESS_STORAGE[job_id] = job
            WEBSOCKET_CONNECTIONS[job_id] = set()

        return job_id

    @staticmethod
    def create_audio_job(user_id: int, dialogue_title: Optional[str] = None) -> str:
        """Create a new standalone audio generation job (TTS + timings, no rendering)."""
        job_id = uuid4().hex

        job = AudioJobProgress(
            job_id=job_id,
            user_id=user_id,
            dialogue_title=dialogue_title,
            created_at=datetime.now(),
        )

        with STORAGE_LOCK:
            PROGRESS_STORAGE[job_id] = job
            WEBSOCKET_CONNECTIONS[job_id] = set()

        return job_id

    @staticmethod
    def create_visual_job(
        user_id: int,
        project_id: str,
        mode: Literal["automatic", "review"],
        dialogue_title: Optional[str] = None,
        retry_of_job_id: Optional[str] = None,
    ) -> str:
        """Create a new transient post-narration visual-generation job."""
        job_id = uuid4().hex

        job = VisualJobProgress(
            job_id=job_id,
            user_id=user_id,
            project_id=project_id,
            mode=mode,
            dialogue_title=dialogue_title,
            retry_of_job_id=retry_of_job_id,
            created_at=datetime.now(),
        )

        with STORAGE_LOCK:
            PROGRESS_STORAGE[job_id] = job
            WEBSOCKET_CONNECTIONS[job_id] = set()

        return job_id

    @staticmethod
    def get_job(job_id: str) -> Optional[JobProgress]:
        """Retrieve job progress by ID."""
        with STORAGE_LOCK:
            return PROGRESS_STORAGE.get(job_id)
    
    @staticmethod
    def update_job(
        job_id: str,
        status: Optional[JobStatus] = None,
        current_stage: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[dict] = None,
        generation_error: Optional[dict] = None,
        composition_id: Any = _UNSET,
        slots: Any = _UNSET,
        # Deprecated parameters for backward compatibility
        current_subtopic: Optional[int] = None,
        subtopic_title: Optional[str] = None,
        title: Optional[str] = None,  # For setting dialogue_title
    ) -> None:
        """
        Update job progress and broadcast to WebSocket clients.
        
        This method handles both transcript and video jobs.
        """
        with STORAGE_LOCK:
            job = PROGRESS_STORAGE.get(job_id)
            if not job:
                return
            
            # Update common fields
            if status:
                job.status = status
            if current_stage:
                job.current_stage = current_stage
            if error:
                job.error = error
            if result:
                job.result = result
            if generation_error is not None:
                job.generation_error = GenerationErrorPayload.model_validate(
                    generation_error
                )
            
            # Update video/audio-specific fields for single dialogue
            if isinstance(job, (VideoJobProgress, AudioJobProgress)):
                if title:
                    job.dialogue_title = title

            if isinstance(job, VisualJobProgress):
                if composition_id is not _UNSET:
                    job.composition_id = composition_id
                if slots is not _UNSET:
                    job.slots = [
                        slot if isinstance(slot, VisualSlotView) else VisualSlotView.model_validate(slot)
                        for slot in (slots or [])
                    ]
            
            # Mark completion time
            if status in ("completed", "failed", "cancelled"):
                job.completed_at = datetime.now()
            
            # Build update message
            update = ProgressService._build_update_message(job)
        
        # Broadcast to WebSocket clients (outside lock to avoid deadlock)
        ProgressService._schedule_broadcast(job_id, update)

    @staticmethod
    def fail_job(
        job_id: str, error: GenerationError, result: Optional[dict] = None
    ) -> None:
        """Fail a job with both the legacy message and stable error envelope.

        ``result`` is set in the same broadcast as ``status`` (never a
        follow-up call), so no client can observe a settled status with a
        still-null result.
        """

        envelope = error.to_dict()
        ProgressService.update_job(
            job_id=job_id,
            status="failed",
            error=envelope["message"],
            generation_error=envelope,
            result=result,
        )

    @staticmethod
    def cancel_job(job_id: str) -> None:
        """Mark a job cancelled - distinct from failed, and never retryable."""
        ProgressService.update_job(
            job_id=job_id,
            status="cancelled",
        )
    
    @staticmethod
    def _schedule_broadcast(job_id: str, update: ProgressUpdate) -> None:
        """
        Schedule a broadcast in a thread-safe manner.
        
        This method handles broadcasting from both async contexts (where we have
        a running event loop) and sync/thread contexts (where we don't).
        
        Args:
            job_id: Job identifier
            update: Progress update to broadcast
        """
        try:
            # Try to create task in current event loop (async context)
            loop = asyncio.get_running_loop()
            asyncio.create_task(ProgressService._broadcast(job_id, update))
        except RuntimeError:
            # No running loop - we're in a thread context
            # Use the stored main event loop
            if _main_event_loop:
                asyncio.run_coroutine_threadsafe(
                    ProgressService._broadcast(job_id, update),
                    _main_event_loop
                )
            else:
                # Event loop not set - log warning but don't crash
                print(f"⚠️  Warning: No event loop available for progress broadcast (job {job_id})")
                print(f"   Call set_event_loop() during application startup to enable broadcasts from threads")
    
    @staticmethod
    def _build_update_message(job: JobProgress) -> ProgressUpdate:
        """Build a ProgressUpdate message from job state."""
        if job.status == "completed":
            msg_type = "completed"
        elif job.status == "failed":
            msg_type = "error"
        elif job.status == "cancelled":
            msg_type = "cancelled"
        else:
            msg_type = "progress"
        
        # Get dialogue title for video/audio jobs
        dialogue_title = None
        if isinstance(job, (VideoJobProgress, AudioJobProgress)):
            dialogue_title = job.dialogue_title

        visual_fields: Dict[str, Any] = {}
        if isinstance(job, VisualJobProgress):
            visual_fields = {
                "mode": job.mode,
                "project_id": job.project_id,
                "composition_id": job.composition_id,
                "retry_of_job_id": job.retry_of_job_id,
                "slots": job.slots,
            }

        return ProgressUpdate(
            type=msg_type,
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            percentage=job.percentage,
            message=job.message,
            current_stage=job.current_stage,
            dialogue_title=dialogue_title,  # Changed from subtopic fields
            result=job.result if job.status == "completed" else None,
            error=job.error if job.status in ("failed", "cancelled") else None,
            generation_error=(
                job.generation_error if job.status == "failed" else None
            ),
            **visual_fields,
        )
    
    @staticmethod
    async def _broadcast(job_id: str, update: ProgressUpdate) -> None:
        """Send update to all connected WebSocket clients for this job."""
        with STORAGE_LOCK:
            connections = WEBSOCKET_CONNECTIONS.get(job_id, set()).copy()
        
        if not connections:
            return
        
        message = update.model_dump_json()
        dead_connections = set()
        
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.add(ws)
        
        # Remove dead connections
        if dead_connections:
            with STORAGE_LOCK:
                if job_id in WEBSOCKET_CONNECTIONS:
                    WEBSOCKET_CONNECTIONS[job_id] -= dead_connections
    
    @staticmethod
    def add_websocket(job_id: str, websocket) -> None:
        """Register a WebSocket connection for a job."""
        with STORAGE_LOCK:
            if job_id not in WEBSOCKET_CONNECTIONS:
                WEBSOCKET_CONNECTIONS[job_id] = set()
            WEBSOCKET_CONNECTIONS[job_id].add(websocket)
    
    @staticmethod
    def remove_websocket(job_id: str, websocket) -> None:
        """Unregister a WebSocket connection."""
        with STORAGE_LOCK:
            if job_id in WEBSOCKET_CONNECTIONS:
                WEBSOCKET_CONNECTIONS[job_id].discard(websocket)
    
    @staticmethod
    def get_initial_update(job: JobProgress) -> ProgressUpdate:
        """Get the current state as a ProgressUpdate for new WebSocket connections."""
        return ProgressService._build_update_message(job)
    
    @staticmethod
    def cleanup_expired() -> int:
        """Remove jobs older than TTL. Returns count of removed jobs."""
        now = datetime.now()
        with STORAGE_LOCK:
            expired = [
                job_id for job_id, job in PROGRESS_STORAGE.items()
                if (job.completed_at and now - job.completed_at > PROGRESS_TTL) or
                   (not job.completed_at and now - job.created_at > PROGRESS_TTL)
            ]
            for job_id in expired:
                del PROGRESS_STORAGE[job_id]
                if job_id in WEBSOCKET_CONNECTIONS:
                    del WEBSOCKET_CONNECTIONS[job_id]
        
        return len(expired)
    
    @staticmethod
    def get_job_count() -> int:
        """Get the current number of tracked jobs."""
        with STORAGE_LOCK:
            return len(PROGRESS_STORAGE)
