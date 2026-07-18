"""Persistence operations for editor projects and dialogue lines."""

from typing import Dict, List, NotRequired, Optional, Sequence, TypedDict
from uuid import UUID, uuid4

from psycopg2.extensions import cursor as PGCursor

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
                with conn.cursor() as cur:
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
            with conn.cursor() as cur:
                return self._get_project(cur, project_id, user_id, required=False)
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
                with conn.cursor() as cur:
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
                        self._raise_update_error(
                            cur, project_id, line_id, user_id, expected_revision
                        )

                    # Any dialogue edit makes the previously concatenated audio stale.
                    cur.execute(
                        """
                        UPDATE editor_projects
                        SET active_composition_id = NULL, updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (project_id, user_id),
                    )
                    return self._line_from_row(row)
        finally:
            conn.close()

    def _get_project(
        self,
        cur: PGCursor,
        project_id: UUID,
        user_id: int,
        required: bool = True,
    ) -> Optional[Dict[str, object]]:
        """Load one owned project and its ordered dialogue in the same connection.

        The joins expose storage keys for the currently active composition and
        segment; URLs are generated later rather than persisted in Postgres.
        """
        cur.execute(
            """
            SELECT project.id, project.user_id, project.title,
                   project.background_video_id, project.revision,
                   project.active_composition_id, composition.storage_key,
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
                   line.created_at, line.updated_at, segment.storage_key
            FROM dialogue_lines AS line
            LEFT JOIN audio_segments AS segment
              ON segment.id = line.active_segment_id
            WHERE line.project_id = %s
            ORDER BY line.position
            """,
            (project_id,),
        )
        lines = []
        for row in cur.fetchall():
            item = self._line_from_row(row[:11])
            item["active_segment_storage_key"] = row[11]
            lines.append(item)

        return {
            "id": project[0],
            "user_id": project[1],
            "title": project[2],
            "background_video_id": project[3],
            "revision": project[4],
            "active_composition_id": project[5],
            "active_composition_storage_key": project[6],
            "created_at": project[7],
            "updated_at": project[8],
            "dialogue": lines,
        }

    def _raise_update_error(
        self,
        cur: PGCursor,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        """Explain why the conditional UPDATE changed no rows.

        The UPDATE can fail because the resource does not exist, audio generation
        currently owns the line, or another client already advanced its revision.
        Convert those cases into the domain error used by the API's 404/409 response.
        """
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
        if current[1] == "generating":
            raise EditorLineGeneratingError("Dialogue cannot be edited while audio is generating")
        raise EditorRevisionConflictError(
            f"Expected revision {expected_revision}, but current revision is {current[0]}"
        )

    @staticmethod
    def _line_from_row(row: Sequence[object]) -> Dict[str, object]:
        return {
            "id": row[0],
            "position": row[1],
            "caption": row[2],
            "speaker": row[3],
            "emotion": row[4],
            "revision": row[5],
            "audio_status": row[6],
            "audio_error": row[7],
            "active_segment_id": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }
