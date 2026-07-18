"""API contract tests for editor project persistence."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.repositories.editor_repository import EditorRevisionConflictError


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
LINE_ID = UUID("22222222-2222-4222-8222-222222222222")
MISSING_PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")


def test_create_editor_project_starts_backend_generation(client):
    with (
        patch("main.ProgressService.create_transcript_job", return_value="job-1"),
        patch("main._process_transcript_job", new_callable=AsyncMock) as process,
    ):
        response = client.post(
            "/editor/projects",
            json={
                "description": "How photosynthesis works",
                "background_video_id": "minecraft",
            },
        )

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-1"
    process.assert_awaited_once_with(
        job_id="job-1",
        user_id=1,
        description="How photosynthesis works",
        background_video_id="minecraft",
    )


def test_get_editor_project_returns_404(client):
    with patch("main.editor_repository.get_project", return_value=None):
        response = client.get(f"/editor/projects/{MISSING_PROJECT_ID}")

    assert response.status_code == 404


def test_update_editor_line_returns_conflict_for_stale_revision(client):
    with patch(
        "main.editor_repository.update_line",
        side_effect=EditorRevisionConflictError("Expected revision 1, but current revision is 2"),
    ):
        response = client.patch(
            f"/editor/projects/{PROJECT_ID}/lines/{LINE_ID}",
            json={
                "caption": "Updated",
                "speaker": "PETER",
                "emotion": "excited",
                "expected_revision": 1,
            },
        )

    assert response.status_code == 409
    assert "current revision is 2" in response.json()["detail"]


def test_add_editor_line_returns_updated_project(client):
    stored = {"id": PROJECT_ID, "revision": 2, "dialogue": []}
    with patch("main.editor_repository.add_line", return_value=stored) as add:
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/lines",
            json={
                "caption": "New line",
                "speaker": "STEWIE",
                "emotion": "neutral",
                "position": 0,
                "expected_project_revision": 1,
            },
        )

    assert response.status_code == 201
    assert response.json()["project"]["revision"] == 2
    add.assert_called_once()


def test_reorder_requires_current_project_revision(client):
    with patch(
        "main.editor_repository.reorder_lines",
        side_effect=EditorRevisionConflictError(
            "Expected project revision 1, but current revision is 2"
        ),
    ):
        response = client.put(
            f"/editor/projects/{PROJECT_ID}/lines/order",
            json={
                "line_ids": [str(LINE_ID)],
                "expected_project_revision": 1,
            },
        )

    assert response.status_code == 409


def test_create_editor_project_rejects_blank_content(client):
    response = client.post(
        "/editor/projects",
        json={
            "description": "   ",
            "background_video_id": "minecraft",
        },
    )

    assert response.status_code == 422


def test_gemini_result_is_persisted_before_job_completes():
    from frontend_pipeline.script_generation.models import DialogueLine, SingleDialogue
    from main import _process_transcript_job

    generated = SingleDialogue(
        title="Generated project",
        dialogue=[DialogueLine(caption="Hello", speaker="PETER", emotion="neutral")],
    )

    with (
        patch("main.extract_transcripts", return_value=generated),
        patch("main.asyncio.sleep", new_callable=AsyncMock),
        patch(
            "main.editor_repository.create_project",
            return_value={"id": PROJECT_ID},
        ) as create,
        patch("main.ProgressService.update_job") as update_job,
    ):
        asyncio.run(
            _process_transcript_job(
                job_id="job-1",
                user_id=1,
                description="source text",
                background_video_id="minecraft",
            )
        )

    create.assert_called_once_with(
        1,
        "Generated project",
        "minecraft",
        [{"caption": "Hello", "speaker": "PETER", "emotion": "neutral"}],
    )
    assert update_job.call_args.kwargs["status"] == "completed"
    assert update_job.call_args.kwargs["result"] == {"project_id": str(PROJECT_ID)}
