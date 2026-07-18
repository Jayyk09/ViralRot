"""API contract tests for editor project persistence."""

import asyncio
from uuid import UUID
from unittest.mock import AsyncMock, patch

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


def test_create_editor_project(client):
    project_id = PROJECT_ID
    line_id = LINE_ID
    stored = {
        "id": project_id,
        "user_id": 1,
        "title": "Test project",
        "background_video_id": "minecraft",
        "revision": 1,
        "dialogue": [{"id": line_id, "caption": "Hello", "revision": 1}],
    }

    with patch("main.editor_repository.create_project", return_value=stored) as create:
        response = client.post(
            "/editor/projects",
            json={
                "title": "  Test project  ",
                "background_video_id": "minecraft",
                "dialogue": [
                    {"caption": "  Hello  ", "speaker": "PETER", "emotion": "neutral"}
                ],
            },
        )

    assert response.status_code == 201
    assert response.json()["project"]["id"] == str(project_id)
    create.assert_called_once_with(
        1,
        "Test project",
        "minecraft",
        [{"caption": "Hello", "speaker": "PETER", "emotion": "neutral"}],
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


def test_create_editor_project_rejects_empty_dialogue(client):
    response = client.post(
        "/editor/projects",
        json={"title": "Empty", "dialogue": []},
    )

    assert response.status_code == 422


def test_gemini_result_is_persisted_before_job_completes():
    from frontend_pipeline.script_generation.models import DialogueLine, SingleDialogue
    from main import _process_transcript_job

    generated = SingleDialogue(
        title="Generated project",
        dialogue=[
            DialogueLine(caption="Hello", speaker="PETER", emotion="neutral")
        ],
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
                transcript_source="source text",
                transcript_type="text",
                source_type="text",
                temp_file_path=None,
            )
        )

    create.assert_called_once_with(
        1,
        "Generated project",
        None,
        [{"caption": "Hello", "speaker": "PETER", "emotion": "neutral"}],
    )
    assert update_job.call_args.kwargs["status"] == "completed"
    assert update_job.call_args.kwargs["result"]["project_id"] == str(PROJECT_ID)
