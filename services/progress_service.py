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
from typing import Dict, List, Literal, Optional, Set, Union
from uuid import uuid4
from pydantic import BaseModel
import threading

# Type definitions
JobType = Literal["transcript_generation", "video_generation"]
JobStatus = Literal["queued", "processing", "completed", "failed"]
TranscriptStage = Literal["extracting_content", "generating_dialogue"]
VideoStage = Literal["preparing_assets", "audio_generation", "video_assembly", "uploading"]

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

class SubtopicProgress(BaseModel):
    """Progress for a single subtopic in video generation."""
    index: int
    title: str
    stage: Literal["queued", "preparing_assets", "audio_generation", "video_assembly", "uploading", "completed", "failed"]
    error: Optional[str] = None


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
    current_subtopic: int = 0
    total_subtopics: int = 1
    subtopics: Dict[int, SubtopicProgress] = {}
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[dict] = None  # Contains collection_id + video URLs
    
    @property
    def percentage(self) -> int:
        """Calculate overall progress percentage."""
        if self.status == "completed":
            return 100
        if self.status == "failed" or self.total_subtopics == 0:
            return 0
        
        # 4 stages per subtopic
        stages_per_subtopic = 4
        completed_subtopics = max(0, self.current_subtopic - 1)
        total_stages = self.total_subtopics * stages_per_subtopic
        
        # Count completed stages
        completed_stages = completed_subtopics * stages_per_subtopic
        
        # Add progress within current subtopic
        stage_order = ["preparing_assets", "audio_generation", "video_assembly", "uploading"]
        if self.current_stage in stage_order:
            completed_stages += stage_order.index(self.current_stage)
        
        return min(99, int((completed_stages / total_stages) * 100))
    
    @property
    def message(self) -> str:
        """Human-readable progress message."""
        if self.status == "completed":
            return f"All {self.total_subtopics} videos generated successfully!"
        if self.status == "failed":
            return f"Failed: {self.error}"
        if self.current_subtopic == 0:
            return "Initializing video generation..."
        
        stage_messages = {
            "preparing_assets": "Preparing assets",
            "audio_generation": "Generating audio",
            "video_assembly": "Assembling video",
            "uploading": "Uploading to storage",
        }
        stage_msg = stage_messages.get(self.current_stage, self.current_stage)
        
        # Get subtopic title if available
        subtopic = self.subtopics.get(self.current_subtopic)
        title = subtopic.title if subtopic else f"Subtopic {self.current_subtopic}"
        
        return f"{stage_msg} for subtopic {self.current_subtopic}/{self.total_subtopics}: {title}"


class ProgressUpdate(BaseModel):
    """WebSocket message format for progress updates."""
    type: Literal["progress", "completed", "error"]
    job_id: str
    job_type: JobType
    status: JobStatus
    percentage: int
    message: str
    current_stage: Optional[str] = None
    current_subtopic: Optional[int] = None
    total_subtopics: Optional[int] = None
    subtopic_title: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# Union type for storage
JobProgress = Union[TranscriptJobProgress, VideoJobProgress]


# ============ In-Memory Storage ============

PROGRESS_STORAGE: Dict[str, JobProgress] = {}
WEBSOCKET_CONNECTIONS: Dict[str, Set] = {}  # job_id -> Set[WebSocket]
STORAGE_LOCK = threading.Lock()
PROGRESS_TTL = timedelta(hours=1)


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
    def create_video_job(user_id: int, total_subtopics: int, subtopic_titles: Optional[List[str]] = None) -> str:
        """Create a new video generation job."""
        job_id = uuid4().hex
        
        # Build subtopic progress dict
        subtopics = {}
        for i in range(1, total_subtopics + 1):
            title = subtopic_titles[i - 1] if subtopic_titles and i <= len(subtopic_titles) else f"Subtopic {i}"
            subtopics[i] = SubtopicProgress(index=i, title=title, stage="queued")
        
        job = VideoJobProgress(
            job_id=job_id,
            user_id=user_id,
            total_subtopics=total_subtopics,
            subtopics=subtopics,
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
        current_subtopic: Optional[int] = None,
        subtopic_title: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[dict] = None,
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
            
            # Update video-specific fields
            if isinstance(job, VideoJobProgress):
                if current_subtopic is not None:
                    job.current_subtopic = current_subtopic
                
                # Update subtopic progress
                if current_subtopic and current_subtopic > 0 and current_subtopic in job.subtopics:
                    if current_stage:
                        job.subtopics[current_subtopic].stage = current_stage
                    if subtopic_title:
                        job.subtopics[current_subtopic].title = subtopic_title
                    if error:
                        job.subtopics[current_subtopic].error = error
                        job.subtopics[current_subtopic].stage = "failed"
            
            # Mark completion time
            if status in ("completed", "failed"):
                job.completed_at = datetime.now()
            
            # Build update message
            update = ProgressService._build_update_message(job)
        
        # Broadcast to WebSocket clients (outside lock to avoid deadlock)
        ProgressService._schedule_broadcast(job_id, update)
    
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
        else:
            msg_type = "progress"
        
        # Get subtopic info for video jobs
        subtopic_title = None
        current_subtopic = None
        total_subtopics = None
        
        if isinstance(job, VideoJobProgress):
            current_subtopic = job.current_subtopic
            total_subtopics = job.total_subtopics
            if job.current_subtopic and job.current_subtopic in job.subtopics:
                subtopic_title = job.subtopics[job.current_subtopic].title
        
        return ProgressUpdate(
            type=msg_type,
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            percentage=job.percentage,
            message=job.message,
            current_stage=job.current_stage,
            current_subtopic=current_subtopic,
            total_subtopics=total_subtopics,
            subtopic_title=subtopic_title,
            result=job.result if job.status == "completed" else None,
            error=job.error if job.status == "failed" else None,
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
