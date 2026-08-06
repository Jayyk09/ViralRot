"""Video database operations (repository pattern).

This module handles all database operations for videos,
separating data access from business logic.
"""
import re
from typing import Dict, List, Optional
from uuid import UUID

from db import get_db_conn


class VideoRepository:
    """Handle all video database operations.
    
    This class follows the repository pattern, providing a clean
    interface for video data access without mixing in storage
    or business logic concerns.
    """
    
    def insert_video(
        self,
        user_id: int,
        editor_project_id: UUID,
        storage_key: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        collection_id: Optional[int] = None,
    ) -> int:
        """
        Insert video record into database.
        
        Args:
            user_id: Owner user ID
            storage_key: Storage key (R2 key or local path)
            title: Video title
            description: Video description
            collection_id: Optional collection ID
        
        Returns:
            video_id of inserted record
        """
        conn = get_db_conn()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO videos
                        (user_id, editor_project_id, s3_key, video_title, video_description, collection_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (user_id, editor_project_id, storage_key, title, description, collection_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("INSERT INTO videos returned no row")
                return int(row[0])
        finally:
            conn.close()
    
    def get_video_by_id(self, video_id: int, user_id: int) -> Optional[Dict]:
        """
        Get video by ID and user_id.
        
        Args:
            video_id: Video ID
            user_id: User ID (for authorization)
        
        Returns:
            Video dict or None if not found
        """
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, s3_key, video_title, video_description, collection_id, created_at
                    FROM videos
                    WHERE id = %s AND user_id = %s;
                    """,
                    (video_id, user_id),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "user_id": row[1],
                        "storage_key": row[2],
                        "title": row[3],
                        "description": row[4],
                        "collection_id": row[5],
                        "created_at": row[6],
                    }
                return None
        finally:
            conn.close()
    
    def get_user_videos(
        self, user_id: int, offset: int = 0, limit: int = 5
    ) -> List[Dict]:
        """
        Get paginated list of user's videos.
        
        Args:
            user_id: User ID
            offset: Pagination offset
            limit: Maximum videos to return
        
        Returns:
            List of video dicts, newest first
        """
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, s3_key, video_title, video_description, created_at
                    FROM videos
                    WHERE user_id = %s
                    ORDER BY created_at DESC, id DESC
                    OFFSET %s LIMIT %s;
                    """,
                    (user_id, offset, limit),
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "storage_key": row[1],
                        "title": row[2],
                        "description": row[3],
                        "created_at": row[4],
                    }
                    for row in rows
                ]
        finally:
            conn.close()
    
    def get_collection_videos(
        self, collection_id: int, offset: int = 0, limit: int = 50
    ) -> List[Dict]:
        """
        Get all videos in a collection.
        
        Args:
            collection_id: Collection ID
            offset: Pagination offset
            limit: Maximum videos to return
        
        Returns:
            List of video dicts
        """
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, s3_key, video_title, video_description, collection_id, created_at
                    FROM videos
                    WHERE collection_id = %s
                    ORDER BY created_at ASC, id ASC;
                    """,
                    (collection_id,),
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "storage_key": row[2],
                        "title": row[3],
                        "description": row[4],
                        "collection_id": row[5],
                        "created_at": row[6],
                    }
                    for row in rows
                ]
        finally:
            conn.close()
    
    def delete_video(self, video_id: int, user_id: int) -> bool:
        """
        Delete video record from database.
        
        Args:
            video_id: Video ID
            user_id: User ID (for authorization)
        
        Returns:
            True if deleted, False if not found
        """
        conn = get_db_conn()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM videos WHERE id = %s AND user_id = %s",
                    (video_id, user_id),
                )
                return cur.rowcount > 0
        finally:
            conn.close()
    
    def get_video_count(self, user_id: Optional[int] = None) -> int:
        """
        Get total video count.
        
        Args:
            user_id: If provided, count only user's videos
        
        Returns:
            Total video count
        """
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                if user_id:
                    cur.execute(
                        "SELECT COUNT(*) FROM videos WHERE user_id = %s",
                        (user_id,)
                    )
                else:
                    cur.execute("SELECT COUNT(*) FROM videos")
                row = cur.fetchone()
                return row[0] if row else 0
        finally:
            conn.close()
