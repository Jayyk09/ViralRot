"""Focused repository tests for generated-visual lifecycle primitives."""

import os
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import psycopg2
import pytest
from psycopg2 import sql

from services.repositories.editor_repository import (
    EditorClipValidationError,
    EditorRepository,
    EditorStaleCompositionError,
    EditorTimelineOverlapError,
    EditorVisualLifecycleError,
    MediaAssetLimitError,
    generated_clip_geometry,
)

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
COMPOSITION_ID = UUID("77777777-7777-4777-8777-777777777777")
OTHER_COMPOSITION_ID = UUID("88888888-8888-4888-8888-888888888888")
MANUAL_CLIP_ID = UUID("22222222-2222-4222-8222-222222222222")
ASSET_A_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ASSET_B_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def _repository_connection(*, fetchone_rows=(), fetchall_rows=()):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = list(fetchone_rows)
    cursor.fetchall.side_effect = list(fetchall_rows)
    return connection, cursor


def test_capture_and_verify_active_composition_snapshot():
    snapshot = {
        "project_id": PROJECT_ID,
        "title": "Project",
        "project_revision": 4,
        "composition_id": COMPOSITION_ID,
        "duration_ms": 5000,
        "line_manifest": None,
    }
    connection, cursor = _repository_connection(fetchone_rows=[snapshot])

    with patch(
        "services.repositories.editor_repository.get_db_conn",
        return_value=connection,
    ):
        captured = EditorRepository().capture_active_composition(PROJECT_ID, 1)

    assert captured["composition_id"] == COMPOSITION_ID
    assert captured["line_manifest"] == []
    assert "project.active_composition_id" in cursor.execute.call_args.args[0]
    connection.close.assert_called_once()

    repository = EditorRepository()
    with patch.object(
        repository,
        "capture_active_composition",
        return_value={"composition_id": OTHER_COMPOSITION_ID},
    ):
        with pytest.raises(EditorStaleCompositionError):
            repository.verify_active_composition(PROJECT_ID, 1, COMPOSITION_ID)


def test_media_quota_preflight_and_manual_occupancy_queries():
    connection, cursor = _repository_connection(
        fetchone_rows=[{"id": PROJECT_ID}, {"count": 18}]
    )
    with patch(
        "services.repositories.editor_repository.get_db_conn",
        return_value=connection,
    ):
        with pytest.raises(MediaAssetLimitError, match="capacity for 2"):
            EditorRepository().preflight_media_asset_quota(PROJECT_ID, 1, 3)

    occupancy = [
        {
            "id": MANUAL_CLIP_ID,
            "start_ms": 1000,
            "end_ms": 2000,
            "z_index": 4,
        }
    ]
    connection, cursor = _repository_connection(
        fetchone_rows=[{"id": PROJECT_ID}], fetchall_rows=[occupancy]
    )
    with patch(
        "services.repositories.editor_repository.get_db_conn",
        return_value=connection,
    ):
        result = EditorRepository().get_manual_timeline_occupancy(PROJECT_ID, 1)

    assert result == occupancy
    occupancy_sql = cursor.execute.call_args_list[1].args[0]
    assert "origin = 'manual'" in occupancy_sql
    assert "ORDER BY start_ms" in occupancy_sql


def test_generated_geometry_is_horizontally_centered_top_anchored_caps_width_and_fits_height():
    # Top-anchored (not vertically centered) so generated visuals don't sit
    # directly behind captions, which always render at the vertical center.
    assert generated_clip_geometry(1000, 500) == pytest.approx(
        (0.2, 0.05, 0.6)
    )

    x, y, width = generated_clip_geometry(300, 3000)
    normalized_height = width * (3000 / 300) * (1080 / 1920)
    assert x == pytest.approx((1 - width) / 2)
    # A portrait image tall enough to fill the frame has no room for any top
    # margin and is unavoidably placed at y=0.
    assert y == pytest.approx(0)
    assert normalized_height == pytest.approx(1)


class _LifecycleCursor:
    """Small SQL-aware cursor used to assert replacement transaction behavior."""

    def __init__(self, *, active_composition_id=COMPOSITION_ID):
        self.active_composition_id = active_composition_id
        self.statements = []
        self._rows = []

    def execute(self, statement, params=None):
        text = str(statement)
        self.statements.append((text, params))
        if "FROM editor_projects" in text and "FOR UPDATE" in text:
            self._rows = [
                {
                    "id": PROJECT_ID,
                    "revision": 4,
                    "active_composition_id": self.active_composition_id,
                }
            ]
        elif "FROM audio_compositions" in text:
            self._rows = [{"id": COMPOSITION_ID, "duration_ms": 5000}]
        elif "FROM timeline_clips" in text and "origin = 'manual'" in text:
            self._rows = [
                {
                    "id": MANUAL_CLIP_ID,
                    "start_ms": 500,
                    "end_ms": 1500,
                    "z_index": 7,
                }
            ]
        elif "FROM media_assets" in text and "id = ANY" in text:
            requested_ids = set(params[2])
            self._rows = [
                row
                for row in (
                    {"id": ASSET_A_ID, "width_px": 400, "height_px": 400},
                    {"id": ASSET_B_ID, "width_px": 1000, "height_px": 500},
                )
                if row["id"] in requested_ids
            ]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


def _lifecycle_connection(cursor):
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection


def test_atomic_replacement_rechecks_manual_occupancy_and_inserts_fixed_generated_clip():
    cursor = _LifecycleCursor()
    connection = _lifecycle_connection(cursor)
    repository = EditorRepository()
    updated_project = {
        "id": PROJECT_ID,
        "revision": 5,
        "active_composition_id": COMPOSITION_ID,
    }

    with (
        patch(
            "services.repositories.editor_repository.get_db_conn",
            return_value=connection,
        ),
        patch.object(repository, "_get_project", return_value=updated_project) as get,
    ):
        result = repository.replace_generated_timeline_clips(
            PROJECT_ID,
            1,
            COMPOSITION_ID,
            [
                # Rechecked manual occupancy skips this placement but retains its asset.
                {"asset_id": ASSET_A_ID, "start_ms": 0, "end_ms": 1000},
                {"asset_id": ASSET_B_ID, "start_ms": 2000, "end_ms": 3000},
            ],
        )

    assert result == updated_project
    get.assert_called_once_with(cursor, PROJECT_ID, 1)
    statements = [statement for statement, _ in cursor.statements]
    delete_index = next(
        index
        for index, statement in enumerate(statements)
        if "DELETE FROM timeline_clips" in statement
    )
    insert_indexes = [
        index
        for index, statement in enumerate(statements)
        if "INSERT INTO timeline_clips" in statement
    ]
    assert len(insert_indexes) == 1
    assert delete_index < insert_indexes[0]
    assert "origin = 'generated'" in statements[delete_index]
    assert "'aligned', 'generated'" in statements[insert_indexes[0]]

    insert_params = cursor.statements[insert_indexes[0]][1]
    assert insert_params[2:5] == (ASSET_B_ID, 2000, 3000)
    assert insert_params[5:8] == pytest.approx((0.2, 0.05, 0.6))
    assert insert_params[8] == 8  # next layer above the surviving manual clip
    assert insert_params[9] == COMPOSITION_ID

    revision_sql = next(
        statement
        for statement in statements
        if "SET revision = revision + 1" in statement
    )
    assert "active_composition_id" not in revision_sql
    assert all("DELETE FROM media_assets" not in statement for statement in statements)
    connection.close.assert_called_once()


def test_replacement_rejects_empty_overlap_stale_and_out_of_bounds_without_delete():
    repository = EditorRepository()
    with patch(
        "services.repositories.editor_repository.get_db_conn"
    ) as connection_factory:
        with pytest.raises(EditorVisualLifecycleError, match="at least one"):
            repository.replace_generated_timeline_clips(
                PROJECT_ID, 1, COMPOSITION_ID, []
            )
        with pytest.raises(EditorTimelineOverlapError):
            repository.replace_generated_timeline_clips(
                PROJECT_ID,
                1,
                COMPOSITION_ID,
                [
                    {"asset_id": ASSET_A_ID, "start_ms": 0, "end_ms": 1000},
                    {"asset_id": ASSET_B_ID, "start_ms": 999, "end_ms": 2000},
                ],
            )
    connection_factory.assert_not_called()

    stale_cursor = _LifecycleCursor(active_composition_id=OTHER_COMPOSITION_ID)
    with patch(
        "services.repositories.editor_repository.get_db_conn",
        return_value=_lifecycle_connection(stale_cursor),
    ):
        with pytest.raises(EditorStaleCompositionError):
            repository.replace_generated_timeline_clips(
                PROJECT_ID,
                1,
                COMPOSITION_ID,
                [{"asset_id": ASSET_A_ID, "start_ms": 0, "end_ms": 1000}],
            )
    assert all(
        "DELETE FROM timeline_clips" not in statement
        for statement, _ in stale_cursor.statements
    )

    bounds_cursor = _LifecycleCursor()
    with patch(
        "services.repositories.editor_repository.get_db_conn",
        return_value=_lifecycle_connection(bounds_cursor),
    ):
        with pytest.raises(EditorClipValidationError, match="end_ms"):
            repository.replace_generated_timeline_clips(
                PROJECT_ID,
                1,
                COMPOSITION_ID,
                [
                    {
                        "asset_id": ASSET_A_ID,
                        "start_ms": 4500,
                        "end_ms": 5500,
                    }
                ],
            )
    assert all(
        "DELETE FROM timeline_clips" not in statement
        for statement, _ in bounds_cursor.statements
    )


def _postgres_candidates():
    return list(
        dict.fromkeys(
            candidate.strip("'\"")
            for candidate in (
                os.getenv("REPOSITORY_TEST_DATABASE_URL"),
                os.getenv("TEST_DATABASE_URL"),
                "postgresql:///postgres",
            )
            if candidate
        )
    )


@pytest.fixture
def visual_lifecycle_postgres():
    """Create a disposable schema for a real PostgreSQL lifecycle transaction."""
    schema_name = f"test_visual_lifecycle_{uuid4().hex}"
    database_url = None
    admin = None
    for candidate in _postgres_candidates():
        connection = None
        try:
            connection = psycopg2.connect(candidate, connect_timeout=2)
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
            database_url = candidate
            admin = connection
            break
        except psycopg2.Error:
            if connection is not None:
                connection.close()

    if admin is None:
        pytest.skip(
            "PostgreSQL repository test needs REPOSITORY_TEST_DATABASE_URL, "
            "TEST_DATABASE_URL, or a local PostgreSQL database"
        )

    def connect():
        connection = psycopg2.connect(database_url)
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET search_path TO {}, pg_catalog").format(
                    sql.Identifier(schema_name)
                )
            )
        connection.commit()
        return connection

    setup = connect()
    try:
        with setup:
            with setup.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE editor_projects (
                        id UUID PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        background_video_id TEXT,
                        revision INTEGER NOT NULL DEFAULT 1,
                        active_composition_id UUID,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE dialogue_lines (
                        id UUID PRIMARY KEY,
                        project_id UUID NOT NULL,
                        position INTEGER NOT NULL,
                        caption TEXT NOT NULL,
                        speaker TEXT NOT NULL,
                        emotion TEXT,
                        revision INTEGER NOT NULL DEFAULT 1,
                        audio_status TEXT NOT NULL DEFAULT 'ready',
                        audio_error TEXT,
                        active_segment_id UUID,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE audio_segments (
                        id UUID PRIMARY KEY,
                        storage_key TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        word_timings JSONB NOT NULL DEFAULT '[]'::jsonb
                    );
                    CREATE TABLE audio_compositions (
                        id UUID PRIMARY KEY,
                        project_id UUID NOT NULL,
                        storage_key TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        line_manifest JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE videos (
                        id UUID PRIMARY KEY,
                        editor_project_id UUID NOT NULL,
                        s3_key TEXT,
                        video_title TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE media_assets (
                        id UUID PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        project_id UUID NOT NULL,
                        storage_key TEXT NOT NULL,
                        original_filename TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        byte_size BIGINT NOT NULL,
                        width_px INTEGER NOT NULL,
                        height_px INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'ready',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE timeline_clips (
                        id UUID PRIMARY KEY,
                        project_id UUID NOT NULL,
                        asset_id UUID NOT NULL,
                        start_ms INTEGER NOT NULL,
                        end_ms INTEGER NOT NULL,
                        x DOUBLE PRECISION NOT NULL,
                        y DOUBLE PRECISION NOT NULL,
                        width DOUBLE PRECISION NOT NULL,
                        z_index INTEGER NOT NULL,
                        authored_composition_id UUID,
                        timing_status TEXT NOT NULL DEFAULT 'aligned',
                        origin TEXT NOT NULL,
                        revision INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
        yield connect
    finally:
        setup.close()
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema_name)
                )
            )
        admin.close()


def test_atomic_replacement_contract_on_postgresql(
    visual_lifecycle_postgres, monkeypatch
):
    connect = visual_lifecycle_postgres
    old_generated_clip_id = uuid4()
    old_manual_asset_id = uuid4()
    old_generated_asset_id = uuid4()
    overlapping_asset_id = uuid4()
    replacement_asset_id = uuid4()

    connection = connect()
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audio_compositions
                    (id, project_id, storage_key, duration_ms, line_manifest)
                VALUES (%s, %s, 'composition.mp3', 5000, '[]'::jsonb)
                """,
                (COMPOSITION_ID, PROJECT_ID),
            )
            cursor.execute(
                """
                INSERT INTO editor_projects
                    (id, user_id, title, revision, active_composition_id)
                VALUES (%s, 1, 'Project', 4, %s)
                """,
                (PROJECT_ID, COMPOSITION_ID),
            )
            assets = (
                (old_manual_asset_id, "manual.webp", 600, 600),
                (old_generated_asset_id, "old-generated.webp", 800, 600),
                (overlapping_asset_id, "overlap.webp", 400, 400),
                (replacement_asset_id, "replacement.webp", 1000, 500),
            )
            for asset_id, storage_key, width, height in assets:
                cursor.execute(
                    """
                    INSERT INTO media_assets
                        (id, user_id, project_id, storage_key, original_filename,
                         content_type, byte_size, width_px, height_px)
                    VALUES (%s, 1, %s, %s, 'image.webp', 'image/webp',
                            100, %s, %s)
                    """,
                    (asset_id, PROJECT_ID, storage_key, width, height),
                )
            cursor.execute(
                """
                INSERT INTO timeline_clips
                    (id, project_id, asset_id, start_ms, end_ms, x, y, width,
                     z_index, authored_composition_id, origin)
                VALUES
                    (%s, %s, %s, 500, 1500, 0.1, 0.1, 0.5, 5, %s, 'manual'),
                    (%s, %s, %s, 1600, 2500, 0.1, 0.1, 0.5, 2, %s, 'generated')
                """,
                (
                    MANUAL_CLIP_ID,
                    PROJECT_ID,
                    old_manual_asset_id,
                    COMPOSITION_ID,
                    old_generated_clip_id,
                    PROJECT_ID,
                    old_generated_asset_id,
                    COMPOSITION_ID,
                ),
            )
    connection.close()

    monkeypatch.setattr(
        "services.repositories.editor_repository.get_db_conn", connect
    )
    repository = EditorRepository()

    snapshot = repository.capture_active_composition(PROJECT_ID, 1)
    assert snapshot["composition_id"] == COMPOSITION_ID
    assert repository.preflight_media_asset_quota(PROJECT_ID, 1, 16) == 16
    with pytest.raises(MediaAssetLimitError):
        repository.preflight_media_asset_quota(PROJECT_ID, 1, 17)
    assert repository.get_manual_timeline_occupancy(PROJECT_ID, 1) == [
        {
            "id": MANUAL_CLIP_ID,
            "start_ms": 500,
            "end_ms": 1500,
            "z_index": 5,
        }
    ]

    project = repository.replace_generated_timeline_clips(
        PROJECT_ID,
        1,
        COMPOSITION_ID,
        [
            {"asset_id": overlapping_asset_id, "start_ms": 0, "end_ms": 1000},
            {"asset_id": replacement_asset_id, "start_ms": 3000, "end_ms": 4000},
        ],
    )

    assert project["revision"] == 5
    assert project["active_composition_id"] == COMPOSITION_ID
    assert len(project["media_assets"]) == 4
    clips_by_origin = {clip["origin"]: clip for clip in project["timeline_clips"]}
    assert clips_by_origin["manual"]["id"] == MANUAL_CLIP_ID
    generated = clips_by_origin["generated"]
    assert generated["id"] != old_generated_clip_id
    assert generated["asset_id"] == replacement_asset_id
    assert (generated["start_ms"], generated["end_ms"]) == (3000, 4000)
    assert (generated["x"], generated["y"], generated["width"]) == pytest.approx(
        (0.2, 0.05, 0.6)
    )
    assert generated["z_index"] == 6
    assert generated["authored_composition_id"] == COMPOSITION_ID
    assert all(clip["asset_id"] != overlapping_asset_id for clip in project["timeline_clips"])

    verification = connect()
    with verification.cursor() as cursor:
        cursor.execute(
            "SELECT revision, active_composition_id FROM editor_projects WHERE id = %s",
            (PROJECT_ID,),
        )
        assert cursor.fetchone() == (5, COMPOSITION_ID)
        cursor.execute("SELECT COUNT(*) FROM media_assets WHERE project_id = %s", (PROJECT_ID,))
        assert cursor.fetchone()[0] == 4
    verification.close()
