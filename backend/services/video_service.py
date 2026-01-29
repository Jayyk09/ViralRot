"""High-level video service combining storage and database operations.

This module provides the main interface for video operations,
orchestrating between storage backends and database repositories.
"""
import re
from uuid import uuid4
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional

from storage import get_storage_backend
from .repositories.video_repository import VideoRepository


class VideoService:
    """High-level video operations (storage + database).
    
    This service combines storage operations (S3 or local) with
    database operations to provide a clean, unified interface
    for video management.
    
    Usage:
        service = VideoService()
        
        # Save a new video
        with open("video.mp4", "rb") as f:
            result = service.save_video(
                user_id=1,
                file_obj=f,
                original_filename="video.mp4",
                title="My Video"
            )
        
        # Get video with URL
        video = service.get_video(video_id=1, user_id=1)
        print(video["presigned_url"])
    """
    
    def __init__(self, storage_backend: Optional[str] = None):
        """
        Initialize video service.
        
        Args:
            storage_backend: Override storage backend ('s3' or 'local').
                           If None, uses environment configuration.
        """
        if storage_backend:
            self.storage = get_storage_backend(backend_type=storage_backend, force_new=True)
        else:
            self.storage = get_storage_backend()
        self.repository = VideoRepository()
    
    def save_video(
        self,
        user_id: int,
        file_obj: BinaryIO,
        original_filename: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        collection_id: Optional[int] = None,
    ) -> Dict:
        """
        Complete video save operation: upload to storage + save to database.
        
        Args:
            user_id: User ID who owns the video
            file_obj: Binary file object containing video data
            original_filename: Original filename (used for extension)
            title: Video title
            description: Video description
            collection_id: Optional collection ID
        
        Returns:
            Dict with:
                - video_id: Database ID
                - storage_key: Storage location key
                - access_url: Presigned/access URL
                - title: Video title
                - collection_id: Collection ID if set
        """
        # 1. Generate storage key
        ext = Path(original_filename).suffix or ".mp4"
        video_uuid = uuid4().hex
        storage_key = f"{user_id}/{video_uuid}{ext}"
        
        # 2. Upload to storage backend
        metadata = {"content_type": "video/mp4"}
        self.storage.upload(file_obj, storage_key, metadata)
        
        # 3. Save to database
        video_id = self.repository.insert_video(
            user_id=user_id,
            storage_key=storage_key,
            title=title,
            description=description,
            collection_id=collection_id,
        )
        
        # 4. Generate access URL
        access_url = self.storage.generate_url(storage_key)
        
        return {
            "video_id": video_id,
            "storage_key": storage_key,
            "access_url": access_url,
            "title": title,
            "collection_id": collection_id,
        }
    
    def get_video(self, video_id: int, user_id: int) -> Dict:
        """
        Get video with presigned URL.
        
        Args:
            video_id: Video ID
            user_id: User ID (for authorization)
        
        Returns:
            Video dict with presigned_url added
        
        Raises:
            ValueError: If video not found
        """
        video = self.repository.get_video_by_id(video_id, user_id)
        if not video:
            raise ValueError(f"Video {video_id} not found for user {user_id}")
        
        # Add presigned URL
        video["presigned_url"] = self.storage.generate_url(video["storage_key"])
        return video
    
    def get_user_videos(
        self, user_id: int, offset: int = 0, limit: int = 5
    ) -> List[Dict]:
        """
        Get user videos with presigned URLs.
        
        Args:
            user_id: User ID
            offset: Pagination offset
            limit: Maximum videos to return
        
        Returns:
            List of video dicts with presigned_url added
        """
        videos = self.repository.get_user_videos(user_id, offset, limit)
        
        # Add presigned URLs
        for video in videos:
            video["presigned_url"] = self.storage.generate_url(video["storage_key"])
        
        return videos
    
    def get_collection_videos(
        self, collection_id: int, offset: int = 0, limit: int = 50
    ) -> List[Dict]:
        """
        Get collection videos with presigned URLs, sorted by subtopic number.
        
        Args:
            collection_id: Collection ID
            offset: Pagination offset
            limit: Maximum videos to return
        
        Returns:
            List of video dicts sorted by subtopic number
        """
        videos = self.repository.get_collection_videos(collection_id, offset, limit)
        
        # Add presigned URLs
        for video in videos:
            video["presigned_url"] = self.storage.generate_url(video["storage_key"])
        
        # Sort by subtopic number
        sorted_videos = sorted(videos, key=self._extract_subtopic_number)
        
        # Apply pagination after sorting
        if limit and limit > 0:
            return sorted_videos[offset:offset + limit]
        return sorted_videos[offset:]
    
    def delete_video(self, video_id: int, user_id: int) -> bool:
        """
        Delete video from storage and database.
        
        Args:
            video_id: Video ID
            user_id: User ID (for authorization)
        
        Returns:
            True if deleted, False if not found
        """
        # Get video to find storage key
        video = self.repository.get_video_by_id(video_id, user_id)
        if not video:
            return False
        
        # Delete from storage
        self.storage.delete(video["storage_key"])
        
        # Delete from database
        return self.repository.delete_video(video_id, user_id)
    
    def get_storage_stats(self) -> Dict:
        """
        Get storage statistics.
        
        Returns:
            Dict with storage backend stats
        """
        return self.storage.get_stats()
    
    @staticmethod
    def _extract_subtopic_number(video: Dict) -> int:
        """Extract subtopic number from video description or title."""
        description = video.get('description', '')
        if description:
            match = re.search(r'Subtopic\s*(\d+)/\d+', description, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        title = video.get('title', '')
        if title:
            match = re.search(r'subtopic[_\s]?(\d+)', title, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 999999  # Sort to end if no number found


# Convenience functions for backwards compatibility
def get_user_videos(user_id: int, offset: int = 0, limit: int = 5) -> List[Dict]:
    """Get user videos (backwards compatible function)."""
    service = VideoService()
    return service.get_user_videos(user_id, offset, limit)


def get_collection_videos(collection_id: int, offset: int = 0, limit: int = 50) -> List[Dict]:
    """Get collection videos (backwards compatible function)."""
    service = VideoService()
    return service.get_collection_videos(collection_id, offset, limit)
