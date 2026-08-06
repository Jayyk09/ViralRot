"""API contract tests for visual-generation endpoints and narration guards."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.visual_generation_service import VisualGenerationActiveError

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    from services import visual_generation_service as module

    module._ACTIVE_PROJECT_JOB.clear()
    module._RUNTIME.clear()


def project_with_composition():
    return {
        "id": PROJECT_ID,
        "title": "Project",
        "active_composition_id": UUID("22222222-2222-4222-8222-222222222222"),
    }


def test_start_automatic_visual_generation_requires_active_composition(client):
    with patch(
        "main.editor_repository.get_project",
        return_value={"id": PROJECT_ID, "title": "Project", "active_composition_id": None},
    ):
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )

    assert response.status_code == 409


def test_start_automatic_visual_generation_returns_job(client):
    with (
        patch("main.editor_repository.get_project", return_value=project_with_composition()),
        patch(
            "main.VisualGenerationService.run_automatic", new_callable=AsyncMock
        ) as run_automatic,
    ):
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["job_type"] == "visual_generation"
    assert body["mode"] == "automatic"
    assert "job_id" in body


def test_duplicate_start_returns_409_with_existing_job_id(client):
    with (
        patch("main.editor_repository.get_project", return_value=project_with_composition()),
        patch("main.VisualGenerationService.run_automatic", new_callable=AsyncMock),
    ):
        first = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )
        second = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"]["job_id"] == first.json()["job_id"]


def test_narration_regeneration_is_blocked_while_visual_generation_active(client):
    with (
        patch("main.editor_repository.get_project", return_value=project_with_composition()),
        patch("main.VisualGenerationService.run_automatic", new_callable=AsyncMock),
    ):
        started = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )
        assert started.status_code == 202

        audio_response = client.post(f"/editor/projects/{PROJECT_ID}/audio")

    assert audio_response.status_code == 409
    assert audio_response.json()["detail"]["code"] == "visual_generation_active"


def test_narration_line_edit_is_blocked_while_visual_generation_active(client):
    with (
        patch("main.editor_repository.get_project", return_value=project_with_composition()),
        patch("main.VisualGenerationService.run_automatic", new_callable=AsyncMock),
    ):
        started = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )
        assert started.status_code == 202

        response = client.post(
            f"/editor/projects/{PROJECT_ID}/lines",
            json={
                "caption": "New line",
                "speaker": "PETER",
                "expected_project_revision": 1,
            },
        )

    assert response.status_code == 409


def test_clip_edits_remain_allowed_while_visual_generation_active(client):
    with (
        patch("main.editor_repository.get_project", return_value=project_with_composition()),
        patch("main.VisualGenerationService.run_automatic", new_callable=AsyncMock),
        patch(
            "main.editor_repository.update_timeline_clip",
            return_value={"id": "clip-1", "revision": 2},
        ),
    ):
        started = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )
        assert started.status_code == 202

        response = client.patch(
            f"/editor/projects/{PROJECT_ID}/clips/33333333-3333-4333-8333-333333333333",
            json={"x": 0.3, "expected_revision": 1},
        )

    assert response.status_code == 200


def test_place_selections_endpoint_rejects_unknown_job(client):
    response = client.post(
        f"/editor/projects/{PROJECT_ID}/visual-generations/does-not-exist/place",
        json={"selections": [{"slot_id": "slot-0", "candidate_token": "x"}]},
    )
    assert response.status_code == 404


def test_cancel_is_idempotent_for_settled_jobs(client):
    with (
        patch("main.editor_repository.get_project", return_value=project_with_composition()),
        patch("main.VisualGenerationService.run_automatic", new_callable=AsyncMock),
    ):
        started = client.post(
            f"/editor/projects/{PROJECT_ID}/visual-generations",
            json={"mode": "automatic"},
        )
        job_id = started.json()["job_id"]

    from services.progress_service import ProgressService

    ProgressService.update_job(job_id, status="completed", result={"outcome": "empty_plan"})

    response = client.post(
        f"/editor/projects/{PROJECT_ID}/visual-generations/{job_id}/cancel"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
