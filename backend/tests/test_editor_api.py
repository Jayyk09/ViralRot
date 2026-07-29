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


def test_restore_narrated_script_returns_project_without_visual_mutation(client):
    stored = {
        "id": PROJECT_ID,
        "revision": 4,
        "dialogue": [],
        "media_assets": [{"id": "asset-1"}],
        "timeline_clips": [{"id": "clip-1", "start_ms": 1000, "end_ms": 3000}],
        "exports": [],
    }
    with patch(
        "main.editor_repository.restore_narrated_script", return_value=stored
    ) as restore:
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/restore-narrated-script",
            json={"expected_project_revision": 3},
        )

    assert response.status_code == 200
    assert response.json()["project"]["timeline_clips"] == stored["timeline_clips"]
    restore.assert_called_once_with(PROJECT_ID, 1, 3)


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


def test_project_response_restores_active_composition_timing():
    from main import _editor_project_response

    project = {
        "id": PROJECT_ID,
        "active_composition_id": UUID("44444444-4444-4444-8444-444444444444"),
        "active_composition_storage_key": "composition.mp3",
        "active_composition_duration_ms": 1000,
        "active_composition_line_manifest": [{
            "line_id": str(LINE_ID),
            "start_ms": 0,
            "end_ms": 1000,
            "caption": "Hello",
            "speaker": "PETER",
            "emotion": "neutral",
        }],
        "dialogue": [{
            "id": LINE_ID,
            "active_segment_word_timings": [
                {"word": "Hello", "start": 0.0, "end": 0.8}
            ],
        }],
        "exports": [],
    }
    with patch("main.get_storage_backend") as storage_factory:
        storage_factory.return_value.generate_url.return_value = "https://audio.example/test.mp3"
        response = _editor_project_response(project)

    assert response["active_composition"]["audio_url"].startswith("https://")
    assert response["active_composition"]["line_timings"][0]["duration"] == 1.0
    assert response["active_composition"]["word_timestamps"][0]["word"] == "Hello"


def test_audio_generation_uses_persisted_project(client):
    project = {"id": PROJECT_ID, "title": "Project", "dialogue": []}
    with (
        patch("main.editor_repository.get_project", return_value=project),
        patch("main.ProgressService.create_audio_job", return_value="audio-job"),
        patch("main._process_project_audio_job", new_callable=AsyncMock) as process,
    ):
        response = client.post(f"/editor/projects/{PROJECT_ID}/audio")

    assert response.status_code == 202
    assert response.json()["job_id"] == "audio-job"
    process.assert_awaited_once_with(job_id="audio-job", project_id=PROJECT_ID, user_id=1)


def test_video_generation_rejects_missing_composition(client):
    project = {
        "id": PROJECT_ID,
        "title": "Project",
        "dialogue": [{"id": LINE_ID}],
        "background_video_id": "minecraft",
        "active_composition_id": None,
    }
    with patch("main.editor_repository.get_project", return_value=project):
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/video",
            json={"karaoke_captions": True},
        )

    assert response.status_code == 409
    assert "Regenerate narration" in response.json()["detail"]


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
