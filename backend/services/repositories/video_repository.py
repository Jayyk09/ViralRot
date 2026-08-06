"""Database operations for exports owned through persistent editor projects."""

from typing import Dict, List, Optional
from uuid import UUID

from db import get_db_conn


class VideoRepository:
    """Persist and authorize exports exclusively through ``editor_project_id``."""

    def insert_video(
        self,
        editor_project_id: UUID,
        storage_key: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> int:
        conn = get_db_conn()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO videos
                        (editor_project_id, s3_key, video_title, video_description)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (editor_project_id, storage_key, title, description),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("INSERT INTO videos returned no row")
                return int(row[0])
        finally:
            conn.close()

    def get_video_by_id(self, video_id: int, user_id: int) -> Optional[Dict]:
        """Load one export only when its parent project belongs to ``user_id``."""
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT video.id, video.editor_project_id, video.s3_key,
                           video.video_title, video.video_description, video.created_at
                    FROM videos AS video
                    JOIN editor_projects AS project
                      ON project.id = video.editor_project_id
                    WHERE video.id = %s AND project.user_id = %s
                    """,
                    (video_id, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return {
                    "id": row[0],
                    "editor_project_id": row[1],
                    "storage_key": row[2],
                    "title": row[3],
                    "description": row[4],
                    "created_at": row[5],
                }
        finally:
            conn.close()

    def get_user_videos(
        self, user_id: int, offset: int = 0, limit: int = 5
    ) -> List[Dict]:
        """List exports through their owned projects, newest first."""
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT video.id, video.editor_project_id, video.s3_key,
                           video.video_title, video.video_description, video.created_at
                    FROM videos AS video
                    JOIN editor_projects AS project
                      ON project.id = video.editor_project_id
                    WHERE project.user_id = %s
                    ORDER BY video.created_at DESC, video.id DESC
                    OFFSET %s LIMIT %s
                    """,
                    (user_id, offset, limit),
                )
                return [
                    {
                        "id": row[0],
                        "editor_project_id": row[1],
                        "storage_key": row[2],
                        "title": row[3],
                        "description": row[4],
                        "created_at": row[5],
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()

    def delete_video(self, video_id: int, user_id: int) -> bool:
        """Delete one export only through an owned parent project."""
        conn = get_db_conn()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM videos AS video
                    USING editor_projects AS project
                    WHERE video.id = %s
                      AND project.id = video.editor_project_id
                      AND project.user_id = %s
                    """,
                    (video_id, user_id),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

    def get_video_count(self, user_id: Optional[int] = None) -> int:
        """Count all exports, optionally restricted through project ownership."""
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                if user_id is None:
                    cur.execute("SELECT COUNT(*) FROM videos")
                else:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM videos AS video
                        JOIN editor_projects AS project
                          ON project.id = video.editor_project_id
                        WHERE project.user_id = %s
                        """,
                        (user_id,),
                    )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            conn.close()
