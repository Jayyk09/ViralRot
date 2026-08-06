"""Persistence contract tests for manual/generated timeline clip origin."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg2
import pytest
from psycopg2 import sql

from scripts.migrate_timeline_clip_origin import apply_migration
from services.repositories.editor_repository import EditorRepository

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
ASSET_ID = UUID("55555555-5555-4555-8555-555555555555")
CLIP_ID = UUID("66666666-6666-4666-8666-666666666666")
COMPOSITION_ID = UUID("77777777-7777-4777-8777-777777777777")
BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
CONFIGURED_DATABASE_URL = os.getenv("DATABASE_URL")

PROVIDER_CONTROL_ENV = (
    "GROK_DIALOGUE_TIMEOUT_SECONDS",
    "GROK_VISUAL_PLANNING_TIMEOUT_SECONDS",
    "SERPAPI_SEARCH_TIMEOUT_SECONDS",
    "IMAGE_FETCH_TIMEOUT_SECONDS",
    "DIALOGUE_GENERATION_DEADLINE_SECONDS",
    "VISUAL_PLANNING_DEADLINE_SECONDS",
    "AUTOMATIC_VISUAL_GENERATION_DEADLINE_SECONDS",
    "REVIEW_VISUAL_GENERATION_DEADLINE_SECONDS",
    "FAILED_SLOT_RETRY_DEADLINE_SECONDS",
    "PROVIDER_MAX_ATTEMPTS",
    "PROVIDER_RETRY_BASE_DELAY_SECONDS",
    "PROVIDER_RETRY_MAX_DELAY_SECONDS",
)


def _is_local_database_url(database_url):
    parsed = urlparse(database_url.strip("'\""))
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"} or (
        parsed.hostname is None and parsed.scheme in {"postgres", "postgresql"}
    )


def _postgres_candidates():
    candidates = [
        os.getenv("MIGRATION_TEST_DATABASE_URL"),
        os.getenv("TEST_DATABASE_URL"),
    ]
    if CONFIGURED_DATABASE_URL and _is_local_database_url(CONFIGURED_DATABASE_URL):
        candidates.append(CONFIGURED_DATABASE_URL)

    runtime_url = os.getenv("DATABASE_URL")
    if runtime_url and _is_local_database_url(runtime_url):
        candidates.append(runtime_url)

    # Common Homebrew and repository docker-compose development databases.
    candidates.extend(
        (
            "postgresql:///postgres",
            "postgresql://emory_hacks_user:devpassword@localhost:5432/emory_hacks_db",
        )
    )
    return list(
        dict.fromkeys(
            candidate.strip("'\"") for candidate in candidates if candidate
        )
    )


@pytest.fixture
def isolated_postgres_schema():
    """Connect to PostgreSQL and expose only a disposable per-test schema."""
    schema_name = f"test_timeline_origin_{uuid4().hex}"
    connection = None

    for database_url in _postgres_candidates():
        candidate = None
        try:
            candidate = psycopg2.connect(database_url, connect_timeout=2)
            candidate.autocommit = True
            with candidate.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
            connection = candidate
            break
        except psycopg2.Error:
            if candidate is not None:
                candidate.close()

    if connection is None:
        pytest.skip(
            "PostgreSQL integration test needs MIGRATION_TEST_DATABASE_URL, "
            "TEST_DATABASE_URL, or an available local development database"
        )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET search_path TO {}, pg_catalog").format(
                    sql.Identifier(schema_name)
                )
            )
        connection.autocommit = False
        yield connection
    finally:
        connection.rollback()
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO pg_catalog")
            cursor.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )
        connection.close()


def _repository_connection(fetchone_rows):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = fetchone_rows
    return connection, cursor


def test_clip_patch_converts_generated_origin_to_manual_and_returns_it():
    connection, cursor = _repository_connection(
        [
            {"id": PROJECT_ID},
            {
                "id": CLIP_ID,
                "asset_id": ASSET_ID,
                "start_ms": 1000,
                "end_ms": 4000,
                "x": 0.2,
                "y": 0.2,
                "width": 0.4,
                "z_index": 0,
                "timing_status": "aligned",
                "authored_composition_id": COMPOSITION_ID,
                "origin": "generated",
                "revision": 2,
                "asset_width_px": 1000,
                "asset_height_px": 500,
                "composition_id": COMPOSITION_ID,
                "composition_duration_ms": 10000,
            },
            {
                "id": CLIP_ID,
                "project_id": PROJECT_ID,
                "asset_id": ASSET_ID,
                "start_ms": 1000,
                "end_ms": 4000,
                "x": 0.3,
                "y": 0.2,
                "width": 0.4,
                "z_index": 0,
                "authored_composition_id": COMPOSITION_ID,
                "timing_status": "aligned",
                "origin": "manual",
                "revision": 3,
            },
        ]
    )

    with patch(
        "services.repositories.editor_repository.get_db_conn",
        return_value=connection,
    ):
        clip = EditorRepository().update_timeline_clip(
            PROJECT_ID, CLIP_ID, 1, {"x": 0.3}, expected_revision=2
        )

    update_sql = next(
        call.args[0]
        for call in cursor.execute.call_args_list
        if "UPDATE timeline_clips" in call.args[0]
    )
    assert "origin = 'manual'" in update_sql
    assert "timing_status, origin, revision" in update_sql
    assert clip["origin"] == "manual"


def test_project_clip_reads_include_origin():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [
        {
            "id": PROJECT_ID,
            "user_id": 1,
            "title": "Project",
            "revision": 1,
            "active_composition_id": None,
        },
        None,
    ]
    cursor.fetchall.side_effect = [
        [],
        [],
        [],
        [
            {
                "id": CLIP_ID,
                "project_id": PROJECT_ID,
                "asset_id": ASSET_ID,
                "origin": "generated",
            }
        ],
    ]

    project = EditorRepository()._get_project(cursor, PROJECT_ID, 1)

    clip_query = cursor.execute.call_args_list[4].args[0]
    assert "timing_status, origin" in clip_query
    assert project["timeline_clips"][0]["origin"] == "generated"


def test_origin_migration_is_rerunnable_and_preserves_generated_values():
    sql = (SCRIPTS_DIR / "migrate_timeline_clip_origin.sql").read_text()

    assert "pg_try_advisory_xact_lock" in sql
    assert "SET LOCAL lock_timeout = '5s'" in sql
    assert "ADD COLUMN IF NOT EXISTS origin TEXT" in sql
    assert "SET origin = 'manual'\nWHERE origin IS NULL" in sql
    assert "ALTER COLUMN origin SET DEFAULT 'manual'" in sql
    assert "ALTER COLUMN origin SET NOT NULL" in sql
    assert "IF NOT EXISTS" in sql
    assert "ck_timeline_clips_origin" in sql
    assert "CHECK (origin IN ('manual', 'generated'))" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_timeline_clips_project_origin" in sql
    assert "CREATE INDEX CONCURRENTLY cannot run" in sql


def test_origin_migration_contract_on_postgresql(isolated_postgres_schema):
    connection = isolated_postgres_schema
    old_manual_id, old_generated_id, default_id = (uuid4() for _ in range(3))
    project_id = uuid4()

    # Model the pre-migration table with only the columns this migration needs.
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE timeline_clips (
                    id UUID PRIMARY KEY,
                    project_id UUID NOT NULL
                )
                """
            )
            cursor.executemany(
                "INSERT INTO timeline_clips (id, project_id) VALUES (%s, %s)",
                (
                    (old_manual_id, project_id),
                    (old_generated_id, project_id),
                ),
            )

    apply_migration(connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, origin FROM timeline_clips ORDER BY id")
        assert dict(cursor.fetchall()) == {
            old_manual_id: "manual",
            old_generated_id: "manual",
        }

    # A generated value written after rollout must not be overwritten by a rerun.
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE timeline_clips SET origin = 'generated' WHERE id = %s",
                (old_generated_id,),
            )
    apply_migration(connection)

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO timeline_clips (id, project_id) VALUES (%s, %s) "
                "RETURNING origin",
                (default_id, project_id),
            )
            assert cursor.fetchone()[0] == "manual"
            cursor.execute(
                "SELECT origin FROM timeline_clips WHERE id = %s",
                (old_generated_id,),
            )
            assert cursor.fetchone()[0] == "generated"

            cursor.execute(
                """
                SELECT column_default, is_nullable
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'timeline_clips'
                  AND column_name = 'origin'
                """
            )
            column_default, is_nullable = cursor.fetchone()
            assert column_default in {"'manual'::text", "'manual'"}
            assert is_nullable == "NO"

            cursor.execute(
                """
                SELECT convalidated
                FROM pg_constraint
                WHERE conrelid = 'timeline_clips'::regclass
                  AND conname = 'ck_timeline_clips_origin'
                """
            )
            assert cursor.fetchone() == (True,)

            cursor.execute(
                """
                SELECT index.indisvalid, index.indisready,
                       ARRAY(
                           SELECT attribute.attname
                           FROM unnest(index.indkey) WITH ORDINALITY
                               AS key(attnum, position)
                           JOIN pg_attribute AS attribute
                             ON attribute.attrelid = index.indrelid
                            AND attribute.attnum = key.attnum
                           ORDER BY key.position
                       )
                FROM pg_index AS index
                JOIN pg_class AS index_class
                  ON index_class.oid = index.indexrelid
                JOIN pg_namespace AS namespace
                  ON namespace.oid = index_class.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND index_class.relname = 'idx_timeline_clips_project_origin'
                """
            )
            assert cursor.fetchone() == (True, True, ["project_id", "origin"])

    with pytest.raises(psycopg2.errors.NotNullViolation):
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO timeline_clips (id, project_id, origin) "
                    "VALUES (%s, %s, NULL)",
                    (uuid4(), project_id),
                )

    with pytest.raises(psycopg2.errors.CheckViolation):
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO timeline_clips (id, project_id, origin) "
                    "VALUES (%s, %s, 'automatic')",
                    (uuid4(), project_id),
                )


def test_compose_forwards_grok_and_provider_controls_to_both_apps():
    compose = (BACKEND_DIR / "docker-compose.yml").read_text()

    assert compose.count("- XAI_API_KEY=${XAI_API_KEY") == 2
    assert compose.count("- XAI_MODEL=${XAI_MODEL") == 2
    assert compose.count("- SERPAPI_API_KEY=${SERPAPI_API_KEY") == 2
    for name in (
        "MINIMAX_API_KEY",
        "MINIMAX_GROUP_ID",
        "MINIMAX_PETER_VOICE",
        "MINIMAX_STEWIE_VOICE",
    ):
        assert compose.count(f"- {name}=${{{name}") == 2
    assert "GEMINI_API_KEY" not in compose
    assert "ELEVENLABS_API_KEY" not in compose
    assert "Peter_voiceId" not in compose
    assert "Stewie_voiceId" not in compose
    for name in PROVIDER_CONTROL_ENV:
        assert compose.count(f"- {name}=${{{name}") == 2


def test_container_and_local_start_apply_origin_migration_before_api():
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text()
    local_start = (BACKEND_DIR.parent / "start.sh").read_text()
    command = "python scripts/migrate_timeline_clip_origin.py"

    assert command in dockerfile
    assert "python backend/scripts/migrate_timeline_clip_origin.py" in local_start


def test_fresh_media_schema_has_the_origin_contract():
    sql = (SCRIPTS_DIR / "create_media_tables.sql").read_text()

    assert "origin TEXT NOT NULL DEFAULT 'manual'" in sql
    assert "CONSTRAINT ck_timeline_clips_origin" in sql
    assert "CHECK (origin IN ('manual', 'generated'))" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_timeline_clips_project_origin" in sql
