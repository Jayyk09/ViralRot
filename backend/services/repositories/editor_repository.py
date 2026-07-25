"""Persistence operations for editor projects and dialogue lines."""

import json
from typing import Dict, List, NotRequired, Optional, TypedDict
from uuid import UUID, uuid4

from psycopg2.extras import RealDictCursor

from db import get_db_conn


class EditorLineInput(TypedDict):
    """Validated dialogue fields accepted by the persistence layer."""

    caption: str
    speaker: str
    emotion: NotRequired[Optional[str]]


class EditorProjectNotFoundError(Exception):
    """Raised when a project or line is not owned by the current user."""


class EditorRevisionConflictError(Exception):
    """Raised when an editor write is based on a stale revision."""


class EditorLineGeneratingError(Exception):
    """Raised when a line is edited while its audio is being generated."""


class EditorInvalidOrderError(Exception):
    """Raised when a reorder request does not contain every project line once."""


class EditorRepository:
    """Store and retrieve editor projects using short, explicit transactions."""

    def create_project(
        self,
        user_id: int,
        title: str,
        background_video_id: Optional[str],
        dialogue: List[EditorLineInput],
    ) -> Dict[str, object]:
        project_id = uuid4()
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO editor_projects (id, user_id, title, background_video_id)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (project_id, user_id, title, background_video_id),
                    )
                    for position, line in enumerate(dialogue):
                        cur.execute(
                            """
                            INSERT INTO dialogue_lines
                                (id, project_id, position, caption, speaker, emotion)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                uuid4(),
                                project_id,
                                position,
                                line["caption"],
                                line["speaker"],
                                line.get("emotion"),
                            ),
                        )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def get_project(self, project_id: UUID, user_id: int) -> Optional[Dict[str, object]]:
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                return self._get_project(cur, project_id, user_id, required=False)
        finally:
            conn.close()

    def update_project(
        self,
        project_id: UUID,
        user_id: int,
        title: str,
        background_video_id: Optional[str],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        UPDATE editor_projects
                        SET title = %s,
                            background_video_id = %s,
                            revision = revision + 1,
                            updated_at = NOW()
                        WHERE id = %s AND user_id = %s AND revision = %s
                        RETURNING id
                        """,
                        (title, background_video_id, project_id, user_id, expected_revision),
                    )
                    if cur.fetchone() is None:
                        self._raise_project_update_error(
                            cur, project_id, user_id, expected_revision
                        )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def update_line(
        self,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        caption: str,
        speaker: str,
        emotion: Optional[str],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        UPDATE dialogue_lines AS line
                        SET caption = %s,
                            speaker = %s,
                            emotion = %s,
                            revision = line.revision + 1,
                            audio_status = 'stale',
                            audio_error = NULL,
                            active_segment_id = NULL,
                            updated_at = NOW()
                        FROM editor_projects AS project
                        WHERE line.id = %s
                          AND line.project_id = %s
                          AND project.id = line.project_id
                          AND project.user_id = %s
                          AND line.revision = %s
                          AND line.audio_status <> 'generating'
                        RETURNING line.id, line.position, line.caption, line.speaker,
                                  line.emotion, line.revision, line.audio_status,
                                  line.audio_error, line.active_segment_id,
                                  line.created_at, line.updated_at
                        """,
                        (
                            caption,
                            speaker,
                            emotion,
                            line_id,
                            project_id,
                            user_id,
                            expected_revision,
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        self._raise_line_update_error(
                            cur, project_id, line_id, user_id, expected_revision
                        )

                    self._invalidate_composition(cur, project_id, user_id)
                    return dict(row)
        finally:
            conn.close()

    def add_line(
        self,
        project_id: UUID,
        user_id: int,
        line: EditorLineInput,
        position: Optional[int],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_revision)
                    cur.execute(
                        "SELECT COUNT(*) AS count FROM dialogue_lines WHERE project_id = %s",
                        (project_id,),
                    )
                    count = int(cur.fetchone()["count"])
                    insert_at = count if position is None else position
                    if insert_at < 0 or insert_at > count:
                        raise EditorInvalidOrderError(
                            f"Position must be between 0 and {count}"
                        )

                    cur.execute("SET CONSTRAINTS uq_dialogue_lines_project_position DEFERRED")
                    cur.execute(
                        """
                        UPDATE dialogue_lines
                        SET position = position + 1, updated_at = NOW()
                        WHERE project_id = %s AND position >= %s
                        """,
                        (project_id, insert_at),
                    )
                    cur.execute(
                        """
                        INSERT INTO dialogue_lines
                            (id, project_id, position, caption, speaker, emotion)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uuid4(),
                            project_id,
                            insert_at,
                            line["caption"],
                            line["speaker"],
                            line.get("emotion"),
                        ),
                    )
                    self._advance_project_revision(cur, project_id, user_id)
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def delete_line(
        self,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_revision)
                    cur.execute(
                        """
                        DELETE FROM dialogue_lines
                        WHERE id = %s AND project_id = %s
                        RETURNING position
                        """,
                        (line_id, project_id),
                    )
                    deleted = cur.fetchone()
                    if deleted is None:
                        raise EditorProjectNotFoundError("Dialogue line not found")

                    cur.execute("SET CONSTRAINTS uq_dialogue_lines_project_position DEFERRED")
                    cur.execute(
                        """
                        UPDATE dialogue_lines
                        SET position = position - 1, updated_at = NOW()
                        WHERE project_id = %s AND position > %s
                        """,
                        (project_id, deleted["position"]),
                    )
                    self._advance_project_revision(cur, project_id, user_id)
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def reorder_lines(
        self,
        project_id: UUID,
        user_id: int,
        line_ids: List[UUID],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_revision)
                    cur.execute(
                        "SELECT id FROM dialogue_lines WHERE project_id = %s ORDER BY position FOR UPDATE",
                        (project_id,),
                    )
                    current_ids = [row["id"] for row in cur.fetchall()]
                    if len(line_ids) != len(set(line_ids)) or set(line_ids) != set(current_ids):
                        raise EditorInvalidOrderError(
                            "line_ids must contain every project dialogue line exactly once"
                        )

                    cur.execute("SET CONSTRAINTS uq_dialogue_lines_project_position DEFERRED")
                    for position, line_id in enumerate(line_ids):
                        cur.execute(
                            """
                            UPDATE dialogue_lines
                            SET position = %s, updated_at = NOW()
                            WHERE id = %s AND project_id = %s
                            """,
                            (position, line_id, project_id),
                        )
                    self._advance_project_revision(cur, project_id, user_id)
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def _get_project(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        user_id: int,
        required: bool = True,
    ) -> Optional[Dict[str, object]]:
        """Load one owned project and its ordered dialogue in the same connection."""
        cur.execute(
            """
            SELECT project.id, project.user_id, project.title,
                   project.background_video_id, project.revision,
                   project.active_composition_id,
                   composition.storage_key AS active_composition_storage_key,
                   composition.duration_ms AS active_composition_duration_ms,
                   composition.line_manifest AS active_composition_line_manifest,
                   project.created_at, project.updated_at
            FROM editor_projects AS project
            LEFT JOIN audio_compositions AS composition
              ON composition.id = project.active_composition_id
            WHERE project.id = %s AND project.user_id = %s
            """,
            (project_id, user_id),
        )
        project = cur.fetchone()
        if project is None:
            if required:
                raise EditorProjectNotFoundError("Editor project not found")
            return None

        cur.execute(
            """
            SELECT line.id, line.position, line.caption, line.speaker,
                   line.emotion, line.revision, line.audio_status,
                   line.audio_error, line.active_segment_id,
                   line.created_at, line.updated_at,
                   segment.storage_key AS active_segment_storage_key,
                   segment.duration_ms AS active_segment_duration_ms,
                   segment.word_timings AS active_segment_word_timings
            FROM dialogue_lines AS line
            LEFT JOIN audio_segments AS segment
              ON segment.id = line.active_segment_id
            WHERE line.project_id = %s
            ORDER BY line.position
            """,
            (project_id,),
        )
        result = dict(project)
        result["dialogue"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, s3_key AS storage_key, video_title AS title, created_at
            FROM videos
            WHERE editor_project_id = %s AND user_id = %s
            ORDER BY created_at DESC
            """,
            (project_id, user_id),
        )
        result["exports"] = [dict(row) for row in cur.fetchall()]
        return result

    def prepare_audio_generation(
        self, project_id: UUID, user_id: int
    ) -> Dict[str, object]:
        """Claim every missing/stale/failed line and return the project snapshot."""
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    project = self._get_project(cur, project_id, user_id)
                    lines = project["dialogue"]
                    if not lines:
                        raise EditorInvalidOrderError("Project has no dialogue lines")
                    if any(line["audio_status"] == "generating" for line in lines):
                        raise EditorLineGeneratingError("Narration generation is already running")
                    line_ids = [
                        line["id"]
                        for line in lines
                        if line["audio_status"] in {"missing", "stale", "failed"}
                        or not line["active_segment_id"]
                    ]
                    if line_ids:
                        cur.execute(
                            """
                            UPDATE dialogue_lines
                            SET audio_status = 'generating', audio_error = NULL, updated_at = NOW()
                            WHERE project_id = %s AND id = ANY(%s)
                            """,
                            (project_id, line_ids),
                        )
                    project["lines_to_generate"] = [
                        line for line in lines if line["id"] in set(line_ids)
                    ]
                    return project
        finally:
            conn.close()

    def complete_audio_segment(
        self,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
        segment_id: UUID,
        storage_key: str,
        duration_ms: int,
        voice_id: str,
        word_timings: List[Dict[str, object]],
    ) -> None:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO audio_segments
                            (id, line_id, storage_key, duration_ms, voice_id, word_timings)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (segment_id, line_id, storage_key, duration_ms, voice_id, json.dumps(word_timings)),
                    )
                    cur.execute(
                        """
                        UPDATE dialogue_lines AS line
                        SET active_segment_id = %s, audio_status = 'ready',
                            audio_error = NULL, updated_at = NOW()
                        FROM editor_projects AS project
                        WHERE line.id = %s AND line.project_id = %s
                          AND project.id = line.project_id AND project.user_id = %s
                          AND line.revision = %s AND line.audio_status = 'generating'
                        """,
                        (segment_id, line_id, project_id, user_id, expected_revision),
                    )
                    if cur.rowcount != 1:
                        raise EditorRevisionConflictError(
                            "Dialogue changed while narration was generating"
                        )
        finally:
            conn.close()

    def fail_audio_segment(
        self, project_id: UUID, line_id: UUID, user_id: int, error: str
    ) -> None:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE dialogue_lines AS line
                        SET audio_status = 'failed', audio_error = %s, updated_at = NOW()
                        FROM editor_projects AS project
                        WHERE line.id = %s AND line.project_id = %s
                          AND project.id = line.project_id AND project.user_id = %s
                        """,
                        (error[:2000], line_id, project_id, user_id),
                    )
        finally:
            conn.close()

    def get_composition_inputs(
        self, project_id: UUID, user_id: int
    ) -> List[Dict[str, object]]:
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT line.id AS line_id, line.position, line.caption,
                           line.speaker, line.emotion, line.audio_status,
                           segment.id AS segment_id, segment.storage_key,
                           segment.duration_ms, segment.word_timings
                    FROM dialogue_lines AS line
                    JOIN editor_projects AS project ON project.id = line.project_id
                    LEFT JOIN audio_segments AS segment ON segment.id = line.active_segment_id
                    WHERE line.project_id = %s AND project.user_id = %s
                    ORDER BY line.position
                    """,
                    (project_id, user_id),
                )
                rows = [dict(row) for row in cur.fetchall()]
                if not rows or any(
                    row["audio_status"] != "ready" or not row["segment_id"]
                    for row in rows
                ):
                    raise EditorRevisionConflictError(
                        "Every dialogue line needs ready narration"
                    )
                return rows
        finally:
            conn.close()

    def activate_composition(
        self,
        project_id: UUID,
        user_id: int,
        composition_id: UUID,
        storage_key: str,
        duration_ms: int,
        line_manifest: List[Dict[str, object]],
    ) -> None:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO audio_compositions
                            (id, project_id, storage_key, duration_ms, line_manifest)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        """,
                        (composition_id, project_id, storage_key, duration_ms, json.dumps(line_manifest)),
                    )
                    cur.execute(
                        """
                        UPDATE editor_projects
                        SET active_composition_id = %s, updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (composition_id, project_id, user_id),
                    )
                    if cur.rowcount != 1:
                        raise EditorProjectNotFoundError("Editor project not found")
        finally:
            conn.close()

    def _lock_project(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        cur.execute(
            "SELECT revision FROM editor_projects WHERE id = %s AND user_id = %s FOR UPDATE",
            (project_id, user_id),
        )
        project = cur.fetchone()
        if project is None:
            raise EditorProjectNotFoundError("Editor project not found")
        if project["revision"] != expected_revision:
            raise EditorRevisionConflictError(
                f"Expected project revision {expected_revision}, but current revision is {project['revision']}"
            )

    def _advance_project_revision(
        self, cur: RealDictCursor, project_id: UUID, user_id: int
    ) -> None:
        cur.execute(
            """
            UPDATE editor_projects
            SET revision = revision + 1,
                active_composition_id = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (project_id, user_id),
        )

    def _invalidate_composition(
        self, cur: RealDictCursor, project_id: UUID, user_id: int
    ) -> None:
        cur.execute(
            """
            UPDATE editor_projects
            SET active_composition_id = NULL, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (project_id, user_id),
        )

    def _raise_project_update_error(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        cur.execute(
            "SELECT revision FROM editor_projects WHERE id = %s AND user_id = %s",
            (project_id, user_id),
        )
        current = cur.fetchone()
        if current is None:
            raise EditorProjectNotFoundError("Editor project not found")
        raise EditorRevisionConflictError(
            f"Expected project revision {expected_revision}, but current revision is {current['revision']}"
        )

    def _raise_line_update_error(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        """Classify why the conditional line update changed no rows."""
        cur.execute(
            """
            SELECT line.revision, line.audio_status
            FROM dialogue_lines AS line
            JOIN editor_projects AS project ON project.id = line.project_id
            WHERE line.id = %s AND line.project_id = %s AND project.user_id = %s
            """,
            (line_id, project_id, user_id),
        )
        current = cur.fetchone()
        if current is None:
            raise EditorProjectNotFoundError("Editor project or dialogue line not found")
        if current["audio_status"] == "generating":
            raise EditorLineGeneratingError(
                "Dialogue cannot be edited while audio is generating"
            )
        raise EditorRevisionConflictError(
            f"Expected revision {expected_revision}, but current revision is {current['revision']}"
        )
