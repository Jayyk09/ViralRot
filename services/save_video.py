from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import mimetypes
import re
from typing import BinaryIO, Dict, Any, List, Optional

import boto3

from db import get_db_conn  # shared DB connection

BUCKET_NAME = "emory-hacks-video-bucket"

# Reuse one S3 client for the whole program
s3 = boto3.client("s3")  # uses your AWS configured creds


def upload_video_to_s3(
    file_obj: BinaryIO,
    original_filename: str,
    user_id: int,
) -> str:
    """
    Upload a file-like object to S3 under {user_id}/{uuid}{ext}
    and return the S3 key to store in your DB.
    """
    # Get extension from filename (.mp4, .mov, etc.). Default to .mp4 if none.
    ext = Path(original_filename).suffix or ".mp4"

    # Guess MIME type, fallback to binary
    content_type, _ = mimetypes.guess_type(original_filename)
    if content_type is None:
        content_type = "application/octet-stream"

    # Generate a unique video id
    video_id = uuid4().hex

    # This is the S3 key (path inside the bucket)
    key = f"{user_id}/{video_id}{ext}"

    # Make sure we're at the start of the file
    file_obj.seek(0)

    # Upload the file object
    s3.upload_fileobj(
        Fileobj=file_obj,
        Bucket=BUCKET_NAME,
        Key=key,
        ExtraArgs={"ContentType": content_type},
    )

    return key


def add_video(
    user_id: int,
    file_obj: BinaryIO,
    original_filename: str,
    title: str | None = None,
    description: str | None = None,
    collection_id: Optional[int] = None,
) -> int:
    """
    High-level function:
    - uploads file object to S3
    - inserts row into videos table
    Returns the new video id.
    
    Args:
        user_id: User who owns the video
        file_obj: File-like object containing video data
        original_filename: Original filename (for extension)
        title: Video title
        description: Video description
        collection_id: Optional collection ID to group this video with others
    """
    s3_key = upload_video_to_s3(file_obj, original_filename, user_id)

    conn = get_db_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO videos (user_id, s3_key, video_title, video_description, collection_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (user_id, s3_key, title, description, collection_id),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("INSERT INTO videos RETURNING id returned no row")
            video_id = row[0]
    finally:
        conn.close()

    return int(video_id)


def get_video(user_id: int, video_id: int) -> Dict[str, Any]:
    """
    Retrieve a video row by user_id and video_id, then:
    - look up its s3_key
    - generate a presigned S3 URL
    Returns a dict with DB fields + 'presigned_url'.
    Raises ValueError if not found.
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
    finally:
        conn.close()

    if row is None:
        raise ValueError("Video not found for given user_id and video_id")

    vid_id, user_id_db, s3_key, title, desc, coll_id, created_at = row

    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": s3_key},
        ExpiresIn=3600,  # 1 hour
    )

    return {
        "id": vid_id,
        "user_id": user_id_db,
        "s3_key": s3_key,
        "video_title": title,
        "video_description": desc,
        "collection_id": coll_id,
        "created_at": created_at,
        "presigned_url": presigned_url,
    }


def get_user_videos(
    user_id: int,
    offset: int = 0,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Return up to `limit` videos for a given user, starting at `offset`,
    each with a presigned URL.

    Ordered by newest first (created_at DESC, id DESC).
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, s3_key, video_title, video_description, collection_id, created_at
                FROM videos
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC
                OFFSET %s
                LIMIT %s;
                """,
                (user_id, offset, limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    videos: List[Dict[str, Any]] = []
    for vid_id, s3_key, title, desc, coll_id, created_at in rows:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": s3_key},
            ExpiresIn=3600,  # 1 hour
        )
        videos.append(
            {
                "id": vid_id,
                "title": title,
                "description": desc,
                "collection_id": coll_id,
                "created_at": created_at,
                "presigned_url": presigned_url,
            }
        )

    return videos


def _extract_subtopic_number_from_video(video: Dict[str, Any]) -> int:
    """Extract subtopic number from video description, otherwise return a high number."""
    # Check description first for "Subtopic X/Y" pattern
    description = video.get('description', '')
    if description:
        match = re.search(r'Subtopic\s*(\d+)/\d+', description, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    # Check title for patterns like "subtopic_1", "subtopic 1", or numbers
    title = video.get('title', '')
    if title:
        match = re.search(r'subtopic[_\s]?(\d+)', title, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    # If no explicit subtopic, return a high number to sort to the end
    return 999999


def get_collection_videos(
    collection_id: int,
    offset: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Get all videos in a collection.
    
    Returns:
        List of video dicts with presigned URLs, ordered by subtopic number (1→n)
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
    finally:
        conn.close()

    # Build video list with presigned URLs
    all_videos: List[Dict[str, Any]] = []
    for vid_id, user_id, s3_key, title, desc, coll_id, created_at in rows:
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": s3_key},
            ExpiresIn=3600,
        )
        all_videos.append(
            {
                "id": vid_id,
                "user_id": user_id,
                "title": title,
                "description": desc,
                "collection_id": coll_id,
                "created_at": created_at,
                "presigned_url": presigned_url,
            }
        )
    
    # Sort by subtopic number (1→n)
    sorted_videos = sorted(all_videos, key=_extract_subtopic_number_from_video)
    
    # Apply pagination after sorting
    if limit and limit > 0:
        paginated_videos = sorted_videos[offset:offset + limit]
    else:
        paginated_videos = sorted_videos[offset:]

    return paginated_videos
