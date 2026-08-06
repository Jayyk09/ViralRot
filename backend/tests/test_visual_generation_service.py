"""Orchestration tests for post-narration visual generation."""

import asyncio
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from services.candidate_token_service import CandidateBinding, CandidateTokenSigner
from services.generation_errors import (
    GenerationCancelledError,
    ImageRetrievalError,
    ImageSearchError,
)
from services.image_discovery_service import ReviewImageCandidate
from services.progress_service import PROGRESS_STORAGE, ProgressService
from services.repositories.editor_repository import (
    EditorStaleCompositionError,
    MediaAssetLimitError,
)
from services.visual_generation_service import (
    VisualGenerationActiveError,
    VisualGenerationInvalidRequestError,
    VisualGenerationService,
    claim_visual_run,
    get_active_visual_job_id,
    is_visual_generation_active,
)
from services.visual_planner_models import ResolvedVisualPlan, ResolvedVisualSlot

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = 1
COMPOSITION_ID = uuid4()
LINE_A = str(uuid4())
LINE_B = str(uuid4())


def run(coroutine):
    return asyncio.run(coroutine)


def composition_snapshot(composition_id=COMPOSITION_ID):
    return {
        "project_id": PROJECT_ID,
        "title": "A Useful Lesson",
        "project_revision": 3,
        "composition_id": composition_id,
        "duration_ms": 10_000,
        "line_manifest": [
            {"line_id": LINE_A, "caption": "First line", "start_ms": 0, "end_ms": 2000},
            {"line_id": LINE_B, "caption": "Second line", "start_ms": 2000, "end_ms": 4000},
        ],
    }


def one_slot_plan(composition_id=COMPOSITION_ID):
    return ResolvedVisualPlan(
        composition_id=str(composition_id),
        slots=[
            ResolvedVisualSlot(
                start_line_id=LINE_A,
                end_line_id=LINE_A,
                start_ms=0,
                end_ms=2000,
                search_query="a useful visual",
            )
        ],
    )


def fake_repository(**overrides):
    repo = MagicMock()
    repo.capture_active_composition.return_value = composition_snapshot()
    repo.verify_active_composition.return_value = composition_snapshot()
    repo.preflight_media_asset_quota.return_value = 19
    repo.get_manual_timeline_occupancy.return_value = []
    repo.replace_generated_timeline_clips.return_value = {"id": PROJECT_ID}
    for name, value in overrides.items():
        setattr(repo, name, value)
    return repo


def fake_planner(plan):
    planner = MagicMock()

    async def plan_visuals(*_args, **_kwargs):
        return plan

    planner.plan_visuals.side_effect = plan_visuals
    return planner


def fake_media_assets():
    service = MagicMock()
    service.upload_discovered_image.return_value = {"id": str(uuid4())}
    return service


def fake_ingestion(asset_id=None, raises=None):
    ingestion = MagicMock()

    async def ingest(*_args, **_kwargs):
        if raises is not None:
            raise raises
        return {"id": asset_id or str(uuid4())}

    ingestion.ingest.side_effect = ingest
    return ingestion


def make_service(
    *,
    repository,
    planner,
    image_client=None,
    ingestion=None,
    token_signer=None,
    content_logger=None,
):
    service = VisualGenerationService(
        repository=repository,
        media_assets=fake_media_assets(),
        planner=planner,
        image_client=image_client or MagicMock(),
        token_signer=token_signer or CandidateTokenSigner(b"x" * 32),
        content_logger=content_logger,
    )
    if ingestion is not None:
        service.ingestion = ingestion
    return service


@pytest.fixture(autouse=True)
def clean_registries():
    yield
    PROGRESS_STORAGE.clear()
    from services import visual_generation_service as module

    module._ACTIVE_PROJECT_JOB.clear()
    module._RUNTIME.clear()


class _RankedStub:
    def __init__(self, original_url):
        self.original_url = original_url


def fake_image_client(candidate_url="https://images.example/a.jpg"):
    client = MagicMock()

    async def search_images(*_args, **_kwargs):
        return [_RankedStub(candidate_url)]

    client.search_images.side_effect = search_images
    return client


def test_completed_status_and_result_are_never_broadcast_separately():
    """Regression: a client must never observe status="completed" with a
    still-null result. Two separate update_job() calls (status, then result)
    would create exactly that window; assert every broadcast is consistent.
    """
    from unittest.mock import patch as mock_patch

    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    broadcasts = []

    def record(_job_id, update):
        broadcasts.append(update)

    with mock_patch.object(ProgressService, "_schedule_broadcast", side_effect=record):
        repository = fake_repository()
        service = make_service(
            repository=repository,
            planner=fake_planner(one_slot_plan()),
            image_client=fake_image_client(),
            ingestion=fake_ingestion(),
        )
        run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    settled = [update for update in broadcasts if update.status in ("completed", "failed")]
    assert settled, "expected at least one terminal broadcast"
    for update in settled:
        assert update.result is not None


def test_automatic_total_failure_never_broadcasts_failed_with_null_result():
    from unittest.mock import patch as mock_patch

    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    broadcasts = []
    with mock_patch.object(
        ProgressService, "_schedule_broadcast",
        side_effect=lambda _job_id, update: broadcasts.append(update),
    ):
        service = make_service(
            repository=fake_repository(),
            planner=fake_planner(one_slot_plan()),
            image_client=fake_image_client(),
            ingestion=fake_ingestion(raises=ImageRetrievalError()),
        )
        run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    # By design, `result` only travels over the wire for a "completed" job
    # (see ProgressService._build_update_message); the error message and
    # generation_error envelope carry the failure. The regression this guards
    # against is job.result itself being unset internally, which would have
    # left a later poll/reconnect (which also gates on status=="completed")
    # unable to recover it - confirm the internal job state was set.
    settled = [update for update in broadcasts if update.status == "failed"]
    assert settled
    job = ProgressService.get_job(job_id)
    assert job.result is not None
    assert job.result["outcome"] == "total_failure"


def test_place_selections_never_broadcasts_completed_with_null_result():
    from unittest.mock import patch as mock_patch

    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "review")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    signer = CandidateTokenSigner(b"x" * 32)
    client = MagicMock()

    async def discover_review_candidates(binding, given_signer, **_kwargs):
        return (
            ReviewImageCandidate(
                token=given_signer.sign(binding, "https://images.example/original.jpg"),
                position=1,
                thumbnail_url="https://images.example/thumb.jpg",
                title="A",
                source="Example",
                source_page_url="https://source.example/a",
                original_width=800,
                original_height=600,
                license_details_url=None,
            ),
        )

    client.discover_review_candidates.side_effect = discover_review_candidates
    content_records = []
    service = make_service(
        repository=fake_repository(),
        planner=fake_planner(one_slot_plan()),
        image_client=client,
        ingestion=fake_ingestion(),
        token_signer=signer,
        content_logger=MagicMock(emit=content_records.append),
    )
    run(service.run_review_discovery(job_id, USER_ID, PROJECT_ID))
    job = ProgressService.get_job(job_id)
    token = job.slots[0].candidates[0]["token"]

    broadcasts = []
    with mock_patch.object(
        ProgressService, "_schedule_broadcast",
        side_effect=lambda _job_id, update: broadcasts.append(update),
    ):
        run(
            service.place_selections(
                job_id, USER_ID, PROJECT_ID, [(job.slots[0].slot_id, token)]
            )
        )

    settled = [update for update in broadcasts if update.status == "completed"]
    assert settled
    for update in settled:
        assert update.result is not None
    assert len(content_records) == 1
    assert content_records[0].operation == "image_candidate_selected"
    assert content_records[0].response["query"] == "a useful visual"
    assert content_records[0].response["candidate"] == {
        "position": 1,
        "title": "A",
        "source": "Example",
        "original_width": 800,
        "original_height": 600,
    }
    assert "token" not in str(content_records[0].response)
    assert "https://" not in str(content_records[0].response)


def test_cancelled_review_placement_settles_job_and_releases_project_claim():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "review")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    signer = CandidateTokenSigner(b"x" * 32)
    client = MagicMock()

    async def discover_review_candidates(binding, given_signer, **_kwargs):
        return (
            ReviewImageCandidate(
                token=given_signer.sign(binding, "https://images.example/original.jpg"),
                position=1,
                thumbnail_url="https://images.example/thumb.jpg",
                title="A",
                source="Example",
                source_page_url="https://source.example/a",
                original_width=800,
                original_height=600,
                license_details_url=None,
            ),
        )

    client.discover_review_candidates.side_effect = discover_review_candidates
    service = make_service(
        repository=fake_repository(),
        planner=fake_planner(one_slot_plan()),
        image_client=client,
        ingestion=fake_ingestion(raises=GenerationCancelledError()),
        token_signer=signer,
    )
    run(service.run_review_discovery(job_id, USER_ID, PROJECT_ID))
    job = ProgressService.get_job(job_id)
    token = job.slots[0].candidates[0]["token"]

    with pytest.raises(GenerationCancelledError):
        run(
            service.place_selections(
                job_id, USER_ID, PROJECT_ID, [(job.slots[0].slot_id, token)]
            )
        )

    job = ProgressService.get_job(job_id)
    assert job.status == "cancelled"
    assert job.completed_at is not None
    assert not is_visual_generation_active(USER_ID, PROJECT_ID)
    assert get_active_visual_job_id(USER_ID, PROJECT_ID) is None


def test_automatic_full_success_places_one_generated_clip():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    repository = fake_repository()
    service = make_service(
        repository=repository,
        planner=fake_planner(one_slot_plan()),
        image_client=fake_image_client(),
        ingestion=fake_ingestion(),
    )

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.status == "completed"
    assert job.result["outcome"] == "full_success"
    assert job.result["placed_count"] == 1
    assert job.slots[0].status == "placed"
    repository.replace_generated_timeline_clips.assert_called_once()
    assert not is_visual_generation_active(USER_ID, PROJECT_ID)


def test_automatic_empty_plan_is_a_successful_noop():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    repository = fake_repository()
    empty_plan = ResolvedVisualPlan(composition_id=str(COMPOSITION_ID), slots=[])
    service = make_service(repository=repository, planner=fake_planner(empty_plan))

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.status == "completed"
    assert job.result["outcome"] == "empty_plan"
    repository.replace_generated_timeline_clips.assert_not_called()


def test_automatic_fails_when_composition_changed_before_retrieval():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    repository = fake_repository()
    repository.verify_active_composition.side_effect = EditorStaleCompositionError("stale")
    service = make_service(repository=repository, planner=fake_planner(one_slot_plan()))

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.status == "failed"
    assert job.generation_error.code == "stale_narration_composition"
    repository.replace_generated_timeline_clips.assert_not_called()


def test_automatic_stops_before_fetching_when_quota_is_insufficient():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    repository = fake_repository()
    repository.preflight_media_asset_quota.side_effect = MediaAssetLimitError("full")
    image_client = fake_image_client()
    service = make_service(repository=repository, planner=fake_planner(one_slot_plan()), image_client=image_client)

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.status == "failed"
    image_client.search_images.assert_not_called()


def test_automatic_advances_past_technical_rejection_to_next_candidate():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    client = MagicMock()

    async def search_images(*_args, **_kwargs):
        return [_RankedStub("https://images.example/bad.jpg"), _RankedStub("https://images.example/good.jpg")]

    client.search_images.side_effect = search_images

    ingestion = MagicMock()
    calls = []

    async def ingest(_project_id, _user_id, url, scope=None):
        calls.append(url)
        if url.endswith("bad.jpg"):
            raise ImageRetrievalError()
        return {"id": str(uuid4())}

    ingestion.ingest.side_effect = ingest

    repository = fake_repository()
    service = make_service(
        repository=repository, planner=fake_planner(one_slot_plan()), image_client=client, ingestion=ingestion
    )

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    assert calls == ["https://images.example/bad.jpg", "https://images.example/good.jpg"]
    job = ProgressService.get_job(job_id)
    assert job.result["outcome"] == "full_success"


def test_automatic_total_failure_reports_failed_status_and_keeps_no_clips():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    client = fake_image_client()
    repository = fake_repository()
    service = make_service(
        repository=repository,
        planner=fake_planner(one_slot_plan()),
        image_client=client,
        ingestion=fake_ingestion(raises=ImageRetrievalError()),
    )

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.status == "failed"
    assert job.result["outcome"] == "total_failure"
    repository.replace_generated_timeline_clips.assert_not_called()


def test_automatic_manual_overlap_retains_asset_but_skips_placement():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    repository = fake_repository()
    repository.get_manual_timeline_occupancy.return_value = [
        {"id": uuid4(), "start_ms": 0, "end_ms": 5000, "z_index": 0}
    ]
    service = make_service(
        repository=repository,
        planner=fake_planner(one_slot_plan()),
        image_client=fake_image_client(),
        ingestion=fake_ingestion(),
    )

    run(service.run_automatic(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.slots[0].status == "skipped_manual_overlap"
    repository.replace_generated_timeline_clips.assert_not_called()
    # Total failure outcome here means "nothing placed", but it is not a
    # provider error, so it stays a benign completed empty-placement result.
    assert job.status == "completed"


def test_duplicate_active_run_is_rejected():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "automatic")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    with pytest.raises(VisualGenerationActiveError):
        run(claim_visual_run(USER_ID, PROJECT_ID, "another-job"))

    assert get_active_visual_job_id(USER_ID, PROJECT_ID) == job_id


def test_review_discovery_then_place_selection_replaces_generated_clip():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "review")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))

    signer = CandidateTokenSigner(b"x" * 32)
    repository = fake_repository()

    client = MagicMock()

    async def discover_review_candidates(binding, given_signer, **_kwargs):
        return (
            ReviewImageCandidate(
                token=given_signer.sign(binding, "https://images.example/original.jpg"),
                position=1,
                thumbnail_url="https://images.example/thumb.jpg",
                title="A",
                source="Example",
                source_page_url="https://source.example/a",
                original_width=800,
                original_height=600,
                license_details_url=None,
            ),
        )

    client.discover_review_candidates.side_effect = discover_review_candidates

    service = make_service(
        repository=repository,
        planner=fake_planner(one_slot_plan()),
        image_client=client,
        ingestion=fake_ingestion(),
        token_signer=signer,
    )

    run(service.run_review_discovery(job_id, USER_ID, PROJECT_ID))

    job = ProgressService.get_job(job_id)
    assert job.status == "awaiting_review"
    assert len(job.slots) == 1
    slot = job.slots[0]
    assert slot.status == "awaiting_review"
    assert len(slot.candidates) == 1
    token = slot.candidates[0]["token"]
    assert "original_url" not in slot.candidates[0]

    result = run(
        service.place_selections(job_id, USER_ID, PROJECT_ID, [(slot.slot_id, token)])
    )

    assert result["outcome"] == "full_success"
    repository.replace_generated_timeline_clips.assert_called_once()
    job_after = ProgressService.get_job(job_id)
    assert job_after.status == "completed"
    assert not is_visual_generation_active(USER_ID, PROJECT_ID)


def test_place_selections_rejects_arbitrary_or_mismatched_token():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "review")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))
    ProgressService.update_job(
        job_id,
        status="awaiting_review",
        composition_id=str(COMPOSITION_ID),
        slots=[
            {
                "slot_id": "slot-0",
                "start_line_id": LINE_A,
                "end_line_id": LINE_A,
                "start_ms": 0,
                "end_ms": 2000,
                "query": "a useful visual",
                "status": "awaiting_review",
                "candidates": [],
            }
        ],
    )

    repository = fake_repository()
    service = make_service(repository=repository, planner=fake_planner(one_slot_plan()))

    result = run(
        service.place_selections(
            job_id, USER_ID, PROJECT_ID, [("slot-0", "not-a-real-token")]
        )
    )

    assert result["outcome"] == "total_failure"
    repository.replace_generated_timeline_clips.assert_not_called()


def test_search_slot_updates_candidates_for_review_job():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "review")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))
    ProgressService.update_job(
        job_id,
        status="awaiting_review",
        composition_id=str(COMPOSITION_ID),
        slots=[
            {
                "slot_id": "slot-0",
                "start_line_id": LINE_A,
                "end_line_id": LINE_A,
                "start_ms": 0,
                "end_ms": 2000,
                "query": "old query",
                "status": "awaiting_review",
                "candidates": [],
            }
        ],
    )

    signer = CandidateTokenSigner(b"x" * 32)
    client = MagicMock()
    discovery_kwargs = []

    async def discover_review_candidates(binding, given_signer, **kwargs):
        discovery_kwargs.append(kwargs)
        return (
            ReviewImageCandidate(
                token=given_signer.sign(binding, "https://images.example/new.jpg"),
                position=1,
                thumbnail_url="https://images.example/new-thumb.jpg",
                title="New",
                source="Example",
                source_page_url="https://source.example/new",
                original_width=800,
                original_height=600,
                license_details_url=None,
            ),
        )

    client.discover_review_candidates.side_effect = discover_review_candidates
    service = make_service(
        repository=fake_repository(),
        planner=fake_planner(one_slot_plan()),
        image_client=client,
        token_signer=signer,
    )

    run(service.search_slot(job_id, USER_ID, PROJECT_ID, "slot-0", "new query"))

    job = ProgressService.get_job(job_id)
    assert job.slots[0].query == "new query"
    assert job.slots[0].candidates[0]["title"] == "New"
    assert discovery_kwargs[0]["search_origin"] == "review_manual"


def test_search_slot_rejects_unknown_slot():
    job_id = ProgressService.create_visual_job(USER_ID, str(PROJECT_ID), "review")
    run(claim_visual_run(USER_ID, PROJECT_ID, job_id))
    ProgressService.update_job(
        job_id, status="awaiting_review", composition_id=str(COMPOSITION_ID), slots=[]
    )
    service = make_service(repository=fake_repository(), planner=fake_planner(one_slot_plan()))

    with pytest.raises(VisualGenerationInvalidRequestError):
        run(service.search_slot(job_id, USER_ID, PROJECT_ID, "missing-slot", "q"))
