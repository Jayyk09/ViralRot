"""Transient orchestration for post-narration visual generation.

This module owns the process-local run registry (one active run per
project), drives the planner -> discovery -> retrieval/ingestion -> atomic
placement pipeline, and publishes progress through the existing
``ProgressService``/WebSocket transport. No visual-generation state is
persisted; only successfully ingested media assets and the final atomic
timeline-clip replacement touch the database.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Optional
from uuid import UUID

from services.candidate_token_service import (
    CandidateBinding,
    CandidateBindingMismatchError,
    CandidateTokenError,
    CandidateTokenSigner,
    ExpiredCandidateTokenError,
)
from services.generation_errors import (
    EditorProjectUnavailableError,
    GenerationCancelledError,
    GenerationError,
    ImageSearchError,
    ImageRetrievalError,
    ImageValidationError,
    MediaAssetQuotaExceededError,
    RetryAction,
    StaleNarrationError,
)
from services.grok_dialogue_service import create_xai_responses_client
from services.image_discovery_service import SerpApiGoogleImagesClient
from services.media_service import MediaAssetService
from services.progress_service import ProgressService, VisualSlotView
from services.provider_logging import (
    ContentLogSink,
    ProviderContentRecord,
    StructuredContentLogger,
)
from services.provider_controls import (
    PROVIDER_CONTROL_CONFIG,
    CancellationToken,
    OperationScope,
)
from services.remote_image_fetcher import RemoteImageFetcher, RemoteImageIngestionService
from services.repositories.editor_repository import (
    EditorClipValidationError,
    EditorCompositionRequiredError,
    EditorProjectNotFoundError,
    EditorRepository,
    EditorStaleCompositionError,
    EditorVisualLifecycleError,
    MediaAssetLimitError,
)
from services.visual_planner_models import CapturedNarrationLine, CapturedNarrationSnapshot
from services.visual_planner_service import GrokVisualPlannerService


class VisualGenerationActiveError(GenerationError):
    code = "visual_generation_active"
    default_message = "Visual generation is already running for this project."
    retry_action = RetryAction.NONE


class VisualGenerationNotFoundError(GenerationError):
    code = "visual_generation_not_found"
    default_message = "This visual-generation run is no longer available."
    retry_action = RetryAction.NONE


class VisualGenerationInvalidRequestError(GenerationError):
    code = "visual_generation_invalid_request"
    default_message = "That visual-generation request is invalid."
    retry_action = RetryAction.NONE


# ============ Process-local active-run registry ============
#
# Deliberately process-local: this backend runs as one worker for the local
# MVP (see the resolved provider-limits decision). Distributed coordination
# is a later scaling concern.

@dataclass
class _RuntimeRun:
    user_id: int
    project_id: str
    cancellation: CancellationToken
    task: Optional[asyncio.Task] = None
    project_lock: Optional[asyncio.Lock] = None


_RUNTIME: dict[str, _RuntimeRun] = {}
_PROJECT_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_ACTIVE_PROJECT_JOB: dict[tuple[int, str], str] = {}
_REGISTRY_LOCK = asyncio.Lock()


def _project_key(user_id: int, project_id: UUID | str) -> tuple[int, str]:
    return (user_id, str(project_id))


def get_active_visual_job_id(user_id: int, project_id: UUID | str) -> Optional[str]:
    """Non-blocking lookup used by narration-write guards in ``main.py``."""
    return _ACTIVE_PROJECT_JOB.get(_project_key(user_id, project_id))


def is_visual_generation_active(user_id: int, project_id: UUID | str) -> bool:
    return get_active_visual_job_id(user_id, project_id) is not None


def _get_project_lock(user_id: int, project_id: UUID | str) -> asyncio.Lock:
    key = _project_key(user_id, project_id)
    lock = _PROJECT_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_LOCKS[key] = lock
    return lock


async def claim_visual_run(user_id: int, project_id: UUID | str, job_id: str) -> _RuntimeRun:
    """Register the one active run for this project, or raise if one exists."""
    key = _project_key(user_id, project_id)
    async with _REGISTRY_LOCK:
        existing = _ACTIVE_PROJECT_JOB.get(key)
        if existing is not None:
            raise VisualGenerationActiveError(details={"job_id": existing})
        runtime = _RuntimeRun(
            user_id=user_id,
            project_id=str(project_id),
            cancellation=CancellationToken(),
            project_lock=_get_project_lock(user_id, project_id),
        )
        _ACTIVE_PROJECT_JOB[key] = job_id
        _RUNTIME[job_id] = runtime
        return runtime


async def release_visual_run(user_id: int, project_id: UUID | str, job_id: str) -> None:
    key = _project_key(user_id, project_id)
    async with _REGISTRY_LOCK:
        if _ACTIVE_PROJECT_JOB.get(key) == job_id:
            del _ACTIVE_PROJECT_JOB[key]
        _RUNTIME.pop(job_id, None)


def get_runtime(job_id: str) -> Optional[_RuntimeRun]:
    return _RUNTIME.get(job_id)


def cancel_visual_run(job_id: str) -> bool:
    """Best-effort cooperative cancellation; safe to call repeatedly."""
    runtime = _RUNTIME.get(job_id)
    if runtime is None:
        return False
    runtime.cancellation.cancel("cancelled")
    return True


_SETTLED_STATUSES = {
    "placed",
    "failed",
    "skipped_manual_overlap",
    "skipped_by_user",
    "ingested",
}


def _mapped_repository_error(exc: Exception) -> GenerationError:
    """Translate a repository exception into the stable client-facing envelope."""
    if isinstance(exc, (EditorStaleCompositionError, EditorCompositionRequiredError)):
        return StaleNarrationError()
    if isinstance(exc, MediaAssetLimitError):
        return MediaAssetQuotaExceededError()
    if isinstance(exc, EditorProjectNotFoundError):
        return EditorProjectUnavailableError()
    return GenerationError()


def _outcome_from_slots(slots: list[VisualSlotView]) -> str:
    placed = sum(1 for slot in slots if slot.status == "placed")
    if placed == len(slots) and slots:
        return "full_success"
    if placed > 0:
        return "partial_success"
    return "total_failure"


class VisualGenerationService:
    """Drive one project's visual-generation run end to end."""

    def __init__(
        self,
        *,
        repository: Optional[EditorRepository] = None,
        media_assets: Optional[MediaAssetService] = None,
        planner: Optional[GrokVisualPlannerService] = None,
        image_client: Optional[SerpApiGoogleImagesClient] = None,
        fetcher: Optional[RemoteImageFetcher] = None,
        token_signer: Optional[CandidateTokenSigner] = None,
        content_logger: ContentLogSink | None = None,
    ) -> None:
        self.repository = repository or EditorRepository()
        self.media_assets = media_assets or MediaAssetService(repository=self.repository)
        self.planner = planner or GrokVisualPlannerService(create_xai_responses_client())
        self.image_client = image_client or SerpApiGoogleImagesClient()
        self.fetcher = fetcher or RemoteImageFetcher()
        self.ingestion = RemoteImageIngestionService(self.fetcher, self.media_assets)
        self.token_signer = token_signer or CandidateTokenSigner.from_env()
        self._content_logger = content_logger or StructuredContentLogger()

    # ------------------------------------------------------------------
    # Automatic mode
    # ------------------------------------------------------------------

    async def run_automatic(self, job_id: str, user_id: int, project_id: UUID) -> None:
        runtime = get_runtime(job_id)
        if runtime is None:
            return
        scope = OperationScope.with_timeout(
            PROVIDER_CONTROL_CONFIG.automatic_visual_deadline_seconds,
            cancellation=runtime.cancellation,
        )
        try:
            snapshot, slots = await self._plan(job_id, user_id, project_id, scope)
            if slots is None:
                return  # terminal state already published (empty plan / stale / error)

            self._publish(job_id, current_stage="searching_images", slots=slots)
            await self._discover_and_ingest_automatic(job_id, user_id, project_id, slots, scope)

            await self._finalize_automatic(job_id, user_id, project_id, snapshot.composition_id, slots)
        except GenerationCancelledError:
            ProgressService.cancel_job(job_id)
        except GenerationError as exc:
            ProgressService.fail_job(job_id, exc)
        except Exception:  # noqa: BLE001 - typed envelope only; raw error stays server-side
            ProgressService.fail_job(job_id, GenerationError())
        finally:
            await release_visual_run(user_id, project_id, job_id)

    async def _plan(
        self, job_id: str, user_id: int, project_id: UUID, scope: OperationScope
    ) -> tuple[Optional[CapturedNarrationSnapshot], Optional[list[VisualSlotView]]]:
        self._publish(job_id, current_stage="capturing_narration")
        try:
            captured = await asyncio.to_thread(
                self.repository.capture_active_composition, project_id, user_id
            )
        except EditorCompositionRequiredError as exc:
            ProgressService.fail_job(job_id, _mapped_repository_error(exc))
            return None, None

        snapshot = CapturedNarrationSnapshot(
            composition_id=str(captured["composition_id"]),
            title=str(captured["title"]),
            lines=[
                CapturedNarrationLine(
                    line_id=str(line["line_id"]),
                    line_index=index,
                    caption=str(line["caption"]),
                    start_ms=int(line["start_ms"]),
                    end_ms=int(line["end_ms"]),
                )
                for index, line in enumerate(captured["line_manifest"])
            ],
        )
        self._publish(job_id, composition_id=snapshot.composition_id, current_stage="planning")

        plan = await self.planner.plan_visuals(
            snapshot,
            job_id=job_id,
            project_id=str(project_id),
            user_id=user_id,
            scope=scope,
        )

        if not plan.slots:
            ProgressService.update_job(
                job_id,
                status="completed",
                current_stage="placing_visuals",
                result={
                    "outcome": "empty_plan",
                    "composition_id": snapshot.composition_id,
                    "planned_count": 0,
                    "placed_count": 0,
                    "failed_count": 0,
                },
            )
            return None, None

        try:
            await asyncio.to_thread(
                self.repository.verify_active_composition,
                project_id,
                user_id,
                UUID(snapshot.composition_id),
            )
        except EditorStaleCompositionError as exc:
            ProgressService.fail_job(job_id, _mapped_repository_error(exc))
            return None, None

        try:
            await asyncio.to_thread(
                self.repository.preflight_media_asset_quota,
                project_id,
                user_id,
                len(plan.slots),
            )
        except (MediaAssetLimitError, EditorProjectNotFoundError) as exc:
            ProgressService.fail_job(job_id, _mapped_repository_error(exc))
            return None, None

        slots = [
            VisualSlotView(
                slot_id=f"slot-{index}",
                start_line_id=slot.start_line_id,
                end_line_id=slot.end_line_id,
                start_ms=slot.start_ms,
                end_ms=slot.end_ms,
                query=slot.search_query,
                status="planned",
            )
            for index, slot in enumerate(plan.slots)
        ]
        return snapshot, slots

    async def _discover_and_ingest_automatic(
        self,
        job_id: str,
        user_id: int,
        project_id: UUID,
        slots: list[VisualSlotView],
        scope: OperationScope,
    ) -> None:
        async def process(slot: VisualSlotView) -> None:
            slot.status = "searching"
            self._publish(job_id, current_stage="searching_images", slots=slots)
            try:
                candidates = await self.image_client.search_images(
                    slot.query,
                    job_id=job_id,
                    project_id=str(project_id),
                    user_id=user_id,
                    scope=scope,
                    search_origin="automatic",
                    slot_id=slot.slot_id,
                )
            except GenerationError as exc:
                slot.status = "failed"
                slot.error = exc.envelope
                self._publish(job_id, slots=slots)
                return

            slot.status = "retrieving"
            self._publish(job_id, current_stage="retrieving_images", slots=slots)
            for candidate in candidates:
                try:
                    asset = await self.ingestion.ingest(
                        project_id, user_id, candidate.original_url, scope=scope
                    )
                except (ImageRetrievalError, ImageValidationError):
                    continue  # technical rejection only; try the next ranked result
                slot.status = "ingested"
                slot.asset_id = str(asset["id"])
                self._publish(job_id, slots=slots)
                return

            slot.status = "failed"
            slot.error = ImageRetrievalError().envelope
            self._publish(job_id, slots=slots)

        await asyncio.gather(*(process(slot) for slot in slots))

    async def _finalize_automatic(
        self,
        job_id: str,
        user_id: int,
        project_id: UUID,
        composition_id: str,
        slots: list[VisualSlotView],
    ) -> None:
        self._publish(job_id, current_stage="placing_visuals", slots=slots)
        try:
            await asyncio.to_thread(
                self.repository.verify_active_composition,
                project_id,
                user_id,
                UUID(composition_id),
            )
        except EditorStaleCompositionError as exc:
            ProgressService.fail_job(job_id, _mapped_repository_error(exc))
            return

        placed_count = await self._place_ingested_slots(
            user_id, project_id, composition_id, slots
        )
        self._publish(job_id, slots=slots)

        outcome = _outcome_from_slots(slots)
        result = {
            "outcome": outcome,
            "composition_id": composition_id,
            "planned_count": len(slots),
            "placed_count": placed_count,
            "failed_count": sum(1 for slot in slots if slot.status == "failed"),
            "skipped_count": sum(
                1 for slot in slots if slot.status == "skipped_manual_overlap"
            ),
        }
        if outcome == "total_failure" and not any(
            slot.status == "skipped_manual_overlap" for slot in slots
        ):
            # No slot ever reached a usable image: this is a real failure, not
            # a benign empty outcome, so the client sees a retryable error.
            # `result` is attached in this same call so no observer ever sees
            # status="failed" (or "completed") with a still-null result.
            ProgressService.fail_job(job_id, ImageRetrievalError(), result=result)
            return
        ProgressService.update_job(job_id, status="completed", result=result)

    async def _place_ingested_slots(
        self,
        user_id: int,
        project_id: UUID,
        composition_id: str,
        slots: list[VisualSlotView],
    ) -> int:
        """Filter manual overlaps client-side, then atomically replace."""
        # "placed" slots reach here only during a retry: the atomic replace
        # deletes every still-generated clip, so a prior success must be
        # resubmitted alongside new successes to survive the same call.
        ingested = [slot for slot in slots if slot.status in ("ingested", "placed")]
        if not ingested:
            return 0

        manual_clips = await asyncio.to_thread(
            self.repository.get_manual_timeline_occupancy, project_id, user_id
        )

        def overlaps(slot: VisualSlotView) -> bool:
            return any(
                slot.start_ms < int(manual["end_ms"]) and slot.end_ms > int(manual["start_ms"])
                for manual in manual_clips
            )

        placements = []
        for slot in ingested:
            if overlaps(slot):
                slot.status = "skipped_manual_overlap"
                continue
            placements.append(
                {
                    "asset_id": UUID(slot.asset_id),
                    "start_ms": slot.start_ms,
                    "end_ms": slot.end_ms,
                }
            )

        if not placements:
            return 0

        try:
            await asyncio.to_thread(
                self.repository.replace_generated_timeline_clips,
                project_id,
                user_id,
                UUID(composition_id),
                placements,
            )
        except (EditorStaleCompositionError, EditorVisualLifecycleError, EditorClipValidationError):
            # The atomic transaction independently rechecked and rejected the
            # batch; ingested assets remain, but nothing is placed.
            for slot in ingested:
                if slot.status == "ingested":
                    slot.status = "failed"
                    slot.error = ImageRetrievalError().envelope
            return 0

        placed_ids = {str(p["asset_id"]) for p in placements}
        for slot in ingested:
            if slot.asset_id in placed_ids:
                slot.status = "placed"
        return len(placed_ids)

    # ------------------------------------------------------------------
    # Review mode
    # ------------------------------------------------------------------

    async def run_review_discovery(self, job_id: str, user_id: int, project_id: UUID) -> None:
        runtime = get_runtime(job_id)
        if runtime is None:
            return
        scope = OperationScope.with_timeout(
            PROVIDER_CONTROL_CONFIG.review_visual_deadline_seconds,
            cancellation=runtime.cancellation,
        )
        try:
            snapshot, slots = await self._plan(job_id, user_id, project_id, scope)
            if slots is None:
                await release_visual_run(user_id, project_id, job_id)
                return

            self._publish(job_id, current_stage="searching_images", slots=slots)

            async def discover(slot: VisualSlotView) -> None:
                slot.status = "searching"
                self._publish(job_id, slots=slots)
                binding = CandidateBinding(
                    user_id=user_id,
                    project_id=str(project_id),
                    composition_id=snapshot.composition_id,
                    slot_id=slot.slot_id,
                    query=slot.query,
                )
                try:
                    candidates = await self.image_client.discover_review_candidates(
                        binding,
                        self.token_signer,
                        job_id=job_id,
                        scope=scope,
                        search_origin="review_initial",
                    )
                except GenerationError as exc:
                    slot.status = "failed"
                    slot.error = exc.envelope
                    self._publish(job_id, slots=slots)
                    return
                slot.candidates = [candidate.to_dict() for candidate in candidates]
                slot.status = "awaiting_review"
                self._publish(job_id, slots=slots)

            await asyncio.gather(*(discover(slot) for slot in slots))

            ProgressService.update_job(
                job_id,
                status="awaiting_review",
                current_stage="awaiting_review",
                slots=[_slot_dict(slot) for slot in slots],
            )
            # The review claim stays active (narration remains locked) until the
            # user places or discards; release happens in place()/discard().
        except GenerationCancelledError:
            ProgressService.cancel_job(job_id)
            await release_visual_run(user_id, project_id, job_id)
        except GenerationError as exc:
            ProgressService.fail_job(job_id, exc)
            await release_visual_run(user_id, project_id, job_id)
        except Exception:  # noqa: BLE001
            ProgressService.fail_job(job_id, GenerationError())
            await release_visual_run(user_id, project_id, job_id)

    async def search_slot(
        self, job_id: str, user_id: int, project_id: UUID, slot_id: str, query: str
    ) -> None:
        job = ProgressService.get_job(job_id)
        if job is None or job.job_type != "visual_generation":
            raise VisualGenerationNotFoundError()
        if job.user_id != user_id or job.project_id != str(project_id):
            raise VisualGenerationNotFoundError()
        if job.composition_id is None:
            raise VisualGenerationInvalidRequestError()
        slots = list(job.slots)
        target = next((slot for slot in slots if slot.slot_id == slot_id), None)
        if target is None:
            raise VisualGenerationInvalidRequestError()

        runtime = get_runtime(job_id)
        scope = OperationScope.with_timeout(
            PROVIDER_CONTROL_CONFIG.review_visual_deadline_seconds,
            cancellation=runtime.cancellation if runtime else CancellationToken(),
        )
        binding = CandidateBinding(
            user_id=user_id,
            project_id=str(project_id),
            composition_id=job.composition_id,
            slot_id=slot_id,
            query=query,
        )
        try:
            candidates = await self.image_client.discover_review_candidates(
                binding,
                self.token_signer,
                job_id=job_id,
                scope=scope,
                search_origin="review_manual",
            )
        except GenerationError as exc:
            target.status = "failed"
            target.error = exc.envelope
            ProgressService.update_job(job_id, slots=[_slot_dict(slot) for slot in slots])
            raise
        target.query = binding.query
        target.candidates = [candidate.to_dict() for candidate in candidates]
        target.status = "awaiting_review"
        target.error = None
        ProgressService.update_job(job_id, slots=[_slot_dict(slot) for slot in slots])

    async def place_selections(
        self,
        job_id: str,
        user_id: int,
        project_id: UUID,
        selections: list[tuple[str, str]],
    ) -> dict[str, object]:
        """Place review selections and always settle a started placement run."""
        try:
            return await self._place_selections(
                job_id, user_id, project_id, selections
            )
        except (VisualGenerationInvalidRequestError, VisualGenerationNotFoundError):
            # Invalid review input leaves an awaiting-review job available for
            # correction rather than destroying the user's staged candidates.
            raise
        except GenerationCancelledError:
            ProgressService.cancel_job(job_id)
            raise
        except GenerationError as exc:
            job = ProgressService.get_job(job_id)
            if job is not None and job.status not in ("completed", "failed", "cancelled"):
                ProgressService.fail_job(job_id, exc)
            raise
        except Exception:
            job = ProgressService.get_job(job_id)
            if job is not None and job.status not in ("completed", "failed", "cancelled"):
                ProgressService.fail_job(job_id, GenerationError())
            raise
        finally:
            job = ProgressService.get_job(job_id)
            # A validation failure before placement starts deliberately leaves
            # the review claim active. Every terminal or in-progress placement
            # exit, including cancellation, must release it.
            if job is not None and job.status != "awaiting_review":
                await release_visual_run(user_id, project_id, job_id)

    async def _place_selections(
        self,
        job_id: str,
        user_id: int,
        project_id: UUID,
        selections: list[tuple[str, str]],
    ) -> dict[str, object]:
        """Internal placement implementation after the public cleanup boundary."""
        job = ProgressService.get_job(job_id)
        if job is None or job.job_type != "visual_generation":
            raise VisualGenerationNotFoundError()
        if job.user_id != user_id or job.project_id != str(project_id):
            raise VisualGenerationNotFoundError()
        if job.composition_id is None or job.status != "awaiting_review":
            raise VisualGenerationInvalidRequestError()
        if not selections:
            raise VisualGenerationInvalidRequestError()

        slots = list(job.slots)
        by_id = {slot.slot_id: slot for slot in slots}
        if len({slot_id for slot_id, _ in selections}) != len(selections):
            raise VisualGenerationInvalidRequestError()
        for slot_id, _ in selections:
            if slot_id not in by_id:
                raise VisualGenerationInvalidRequestError()

        for slot in slots:
            if slot.slot_id not in {slot_id for slot_id, _ in selections}:
                if slot.status == "awaiting_review":
                    slot.status = "skipped_by_user"

        runtime = get_runtime(job_id)
        cancellation = runtime.cancellation if runtime else CancellationToken()
        scope = OperationScope.with_timeout(
            PROVIDER_CONTROL_CONFIG.review_visual_deadline_seconds,
            cancellation=cancellation,
        )

        try:
            await asyncio.to_thread(
                self.repository.verify_active_composition,
                project_id,
                user_id,
                UUID(job.composition_id),
            )
        except EditorStaleCompositionError as exc:
            mapped = _mapped_repository_error(exc)
            ProgressService.fail_job(job_id, mapped)
            await release_visual_run(user_id, project_id, job_id)
            raise mapped from exc

        try:
            await asyncio.to_thread(
                self.repository.preflight_media_asset_quota,
                project_id,
                user_id,
                len(selections),
            )
        except (MediaAssetLimitError, EditorProjectNotFoundError) as exc:
            mapped = _mapped_repository_error(exc)
            ProgressService.fail_job(job_id, mapped)
            await release_visual_run(user_id, project_id, job_id)
            raise mapped from exc

        ProgressService.update_job(job_id, status="processing", current_stage="retrieving_images")

        for slot_id, token in selections:
            slot = by_id[slot_id]
            slot.status = "retrieving"
            self._publish(job_id, slots=slots)
            binding = CandidateBinding(
                user_id=user_id,
                project_id=str(project_id),
                composition_id=job.composition_id,
                slot_id=slot_id,
                query=slot.query,
            )
            selected_candidate = next(
                (
                    {
                        key: candidate[key]
                        for key in (
                            "position",
                            "title",
                            "source",
                            "original_width",
                            "original_height",
                        )
                        if candidate.get(key) is not None
                    }
                    for candidate in slot.candidates
                    if candidate.get("token") == token
                ),
                {},
            )
            try:
                verified = self.token_signer.verify(token, binding)
            except (ExpiredCandidateTokenError, CandidateBindingMismatchError, CandidateTokenError) as exc:
                slot.status = "failed"
                slot.error = ImageRetrievalError(details={"reason": "invalid_or_expired_token"}).envelope
                self._publish(job_id, slots=slots)
                continue
            self._content_logger.emit(
                ProviderContentRecord(
                    provider="user",
                    operation="image_candidate_selected",
                    job_id=job_id,
                    project_id=str(project_id),
                    user_id=user_id,
                    search_origin="review_selection",
                    slot_id=slot_id,
                    response={"query": slot.query, "candidate": selected_candidate},
                )
            )
            try:
                asset = await self.ingestion.ingest(
                    project_id, user_id, verified.original_url, scope=scope
                )
            except (ImageRetrievalError, ImageValidationError) as exc:
                slot.status = "failed"
                slot.error = exc.envelope
                self._publish(job_id, slots=slots)
                continue
            slot.status = "ingested"
            slot.asset_id = str(asset["id"])
            self._publish(job_id, slots=slots)

        placed_count = await self._place_ingested_slots(
            user_id, project_id, job.composition_id, slots
        )
        self._publish(job_id, slots=slots)

        outcome = _outcome_from_slots(slots)
        result = {
            "outcome": outcome,
            "composition_id": job.composition_id,
            "planned_count": len(slots),
            "placed_count": placed_count,
            "failed_count": sum(1 for slot in slots if slot.status == "failed"),
            "skipped_count": sum(
                1
                for slot in slots
                if slot.status in ("skipped_manual_overlap", "skipped_by_user")
            ),
        }
        # `result` is attached in the same call as the terminal status so no
        # observer (e.g. a WebSocket client) ever sees a settled status with
        # a still-null result.
        if outcome == "total_failure" and placed_count == 0 and not any(
            slot.status in ("skipped_manual_overlap", "skipped_by_user") for slot in slots
        ):
            ProgressService.fail_job(job_id, ImageRetrievalError(), result=result)
        else:
            ProgressService.update_job(job_id, status="completed", result=result)
        await release_visual_run(user_id, project_id, job_id)
        return result

    async def retry_failed(
        self,
        original_job_id: str,
        user_id: int,
        project_id: UUID,
        slot_ids: Optional[list[str]] = None,
    ) -> str:
        """Clone a settled job onto a fresh one, resetting only eligible slots.

        Successful ("placed") slots are copied unchanged and are resubmitted
        by the atomic replace step so they survive alongside new successes.
        """
        original = ProgressService.get_job(original_job_id)
        if (
            original is None
            or original.job_type != "visual_generation"
            or original.user_id != user_id
            or original.project_id != str(project_id)
        ):
            raise VisualGenerationNotFoundError()
        if not original.composition_id:
            raise VisualGenerationInvalidRequestError()

        retryable_statuses = {"failed", "skipped_manual_overlap"}
        if slot_ids is not None:
            known = {slot.slot_id for slot in original.slots}
            if not slot_ids or any(slot_id not in known for slot_id in slot_ids):
                raise VisualGenerationInvalidRequestError()
            target_ids = set(slot_ids)
        else:
            target_ids = {
                slot.slot_id for slot in original.slots if slot.status in retryable_statuses
            }
        if not target_ids:
            raise VisualGenerationInvalidRequestError()

        new_job_id = ProgressService.create_visual_job(
            user_id,
            str(project_id),
            original.mode,
            dialogue_title=original.dialogue_title,
            retry_of_job_id=original_job_id,
        )
        await claim_visual_run(user_id, project_id, new_job_id)

        cloned_slots = []
        for slot in original.slots:
            if slot.slot_id in target_ids:
                cloned_slots.append(
                    VisualSlotView(
                        slot_id=slot.slot_id,
                        start_line_id=slot.start_line_id,
                        end_line_id=slot.end_line_id,
                        start_ms=slot.start_ms,
                        end_ms=slot.end_ms,
                        query=slot.query,
                        status="planned",
                    )
                )
            else:
                cloned_slots.append(slot.model_copy(deep=True))

        ProgressService.update_job(
            new_job_id, composition_id=original.composition_id, slots=cloned_slots
        )
        return new_job_id

    async def run_automatic_retry(self, job_id: str, user_id: int, project_id: UUID) -> None:
        runtime = get_runtime(job_id)
        if runtime is None:
            return
        scope = OperationScope.with_timeout(
            PROVIDER_CONTROL_CONFIG.failed_slot_retry_deadline_seconds,
            cancellation=runtime.cancellation,
        )
        job = ProgressService.get_job(job_id)
        composition_id = job.composition_id
        try:
            await asyncio.to_thread(
                self.repository.verify_active_composition,
                project_id,
                user_id,
                UUID(composition_id),
            )
        except EditorStaleCompositionError as exc:
            ProgressService.fail_job(job_id, _mapped_repository_error(exc))
            await release_visual_run(user_id, project_id, job_id)
            return

        try:
            slots = list(job.slots)
            retry_targets = [slot for slot in slots if slot.status == "planned"]
            self._publish(job_id, current_stage="searching_images", slots=slots)
            await self._discover_and_ingest_automatic(
                job_id, user_id, project_id, retry_targets, scope
            )
            await self._finalize_automatic(job_id, user_id, project_id, composition_id, slots)
        except GenerationCancelledError:
            ProgressService.cancel_job(job_id)
        except GenerationError as exc:
            ProgressService.fail_job(job_id, exc)
        except Exception:  # noqa: BLE001
            ProgressService.fail_job(job_id, GenerationError())
        finally:
            await release_visual_run(user_id, project_id, job_id)

    async def run_review_retry(self, job_id: str, user_id: int, project_id: UUID) -> None:
        runtime = get_runtime(job_id)
        if runtime is None:
            return
        scope = OperationScope.with_timeout(
            PROVIDER_CONTROL_CONFIG.failed_slot_retry_deadline_seconds,
            cancellation=runtime.cancellation,
        )
        job = ProgressService.get_job(job_id)
        composition_id = job.composition_id
        try:
            await asyncio.to_thread(
                self.repository.verify_active_composition,
                project_id,
                user_id,
                UUID(composition_id),
            )
        except EditorStaleCompositionError as exc:
            ProgressService.fail_job(job_id, _mapped_repository_error(exc))
            await release_visual_run(user_id, project_id, job_id)
            return

        try:
            slots = list(job.slots)
            retry_targets = [slot for slot in slots if slot.status == "planned"]
            self._publish(job_id, current_stage="searching_images", slots=slots)

            async def discover(slot: VisualSlotView) -> None:
                slot.status = "searching"
                self._publish(job_id, slots=slots)
                binding = CandidateBinding(
                    user_id=user_id,
                    project_id=str(project_id),
                    composition_id=composition_id,
                    slot_id=slot.slot_id,
                    query=slot.query,
                )
                try:
                    candidates = await self.image_client.discover_review_candidates(
                        binding,
                        self.token_signer,
                        job_id=job_id,
                        scope=scope,
                        search_origin="review_retry",
                    )
                except GenerationError as exc:
                    slot.status = "failed"
                    slot.error = exc.envelope
                    self._publish(job_id, slots=slots)
                    return
                slot.candidates = [candidate.to_dict() for candidate in candidates]
                slot.status = "awaiting_review"
                self._publish(job_id, slots=slots)

            await asyncio.gather(*(discover(slot) for slot in retry_targets))
            ProgressService.update_job(
                job_id, status="awaiting_review", current_stage="awaiting_review", slots=slots
            )
        except GenerationCancelledError:
            ProgressService.cancel_job(job_id)
            await release_visual_run(user_id, project_id, job_id)
        except GenerationError as exc:
            ProgressService.fail_job(job_id, exc)
            await release_visual_run(user_id, project_id, job_id)
        except Exception:  # noqa: BLE001
            ProgressService.fail_job(job_id, GenerationError())
            await release_visual_run(user_id, project_id, job_id)

    async def discard_review(self, job_id: str, user_id: int, project_id: UUID) -> None:
        job = ProgressService.get_job(job_id)
        if job is None or job.user_id != user_id or job.project_id != str(project_id):
            raise VisualGenerationNotFoundError()
        ProgressService.cancel_job(job_id)
        await release_visual_run(user_id, project_id, job_id)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _publish(self, job_id: str, **fields) -> None:
        if "slots" in fields and fields["slots"] is not None:
            fields["slots"] = [_slot_dict(slot) for slot in fields["slots"]]
        ProgressService.update_job(job_id, **fields)


def _slot_dict(slot: VisualSlotView) -> dict:
    return slot.model_dump(mode="json")


__all__ = [
    "VisualGenerationActiveError",
    "VisualGenerationInvalidRequestError",
    "VisualGenerationNotFoundError",
    "VisualGenerationService",
    "cancel_visual_run",
    "claim_visual_run",
    "get_active_visual_job_id",
    "get_runtime",
    "is_visual_generation_active",
    "release_visual_run",
]
