"""High-level audio service combining storage and database operations.

This module provides the main interface for audio operations,
orchestrating between storage backends and database repositories.
"""
import re
from uuid import uuid4
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional

from storage import get_storage_backend

class AudioService:
    """High-level audio operations (storage + database).
    
    This service combines storage operations (S3 for now) with
    database operations to provide a clean, unified interface
    for audio management.
    
    Usage:
        service = AudioService()
        
        # Save a new audio
        with open("audio.mp3", "rb") as f:
            result = service.save_audio(
                user_id=1,
                file_obj=f,
                original_filename="audio.mp3",
                title="My Audio"
            )
        
        # Get audio with URL
        audio = service.get_audio(audio_id=1, user_id=1)
        print(audio["presigned_url"])
    """
    
    def __init__(self, storage_backend: Optional[str] = None):
        """
        Initialize audio service.
        
        Args:
            storage_backend: Override storage backend ('s3' or 'local').
                           If None, uses environment configuration.
        """
        if storage_backend:
            self.storage = get_storage_backend(backend_type=storage_backend, force_new=True)
        else:
            self.storage = get_storage_backend()
    
    def save_audio(
        self,
        user_id: int,
        file_obj: BinaryIO,
        original_filename: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        collection_id: Optional[int] = None,
    ) -> Dict:
        """
        Complete audio save operation: upload to storage + save to database.
        
        Args:
            user_id: User ID who owns the audio
            file_obj: Binary file object containing audio data
            original_filename: Original filename (used for extension)
            title: audio title
            description: audio description
            collection_id: Optional collection ID
        
        Returns:
            Dict with:
                - audio_id: Database ID
                - storage_key: Storage location key
                - access_url: Presigned/access URL
                - title: audio title
                - collection_id: Collection ID if set
        """
        # 1. Generate storage key
        ext = Path(original_filename).suffix or ".mp3"
        audio_uuid = uuid4().hex
        storage_key = f"{user_id}/{audio_uuid}{ext}"
        
        # 2. Upload to storage backend
        metadata = {"content_type": "audio/mp4"}
        self.storage.upload(file_obj, storage_key, metadata)
        
        # 3. Save to database
        audio_id = self.repository.insert_audio(
            user_id=user_id,
            storage_key=storage_key,
            title=title,
            description=description,
            collection_id=collection_id,
        )
        
        # 4. Generate access URL
        access_url = self.storage.generate_url(storage_key)
        
        return {
            "audio_id": audio_id,
            "storage_key": storage_key,
            "access_url": access_url,
            "title": title,
            "collection_id": collection_id,
        }
    
    def get_audio(self, audio_id: int, user_id: int) -> Dict:
        """
        Get audio with presigned URL.
        
        Args:
            audio_id: audio ID
            user_id: User ID (for authorization)
        
        Returns:
            audio dict with presigned_url added
        
        Raises:
            ValueError: If audio not found
        """
        audio = self.repository.get_audio_by_id(audio_id, user_id)
        if not audio:
            raise ValueError(f"audio {audio_id} not found for user {user_id}")
        
        # Add presigned URL
        audio["presigned_url"] = self.storage.generate_url(audio["storage_key"])
        return audio
    
    def get_user_audios(
        self, user_id: int, offset: int = 0, limit: int = 5
    ) -> List[Dict]:
        """
        Get user audios with presigned URLs.
        
        Args:
            user_id: User ID
            offset: Pagination offset
            limit: Maximum audios to return
        
        Returns:
            List of audio dicts with presigned_url added
        """
        audios = self.repository.get_user_audios(user_id, offset, limit)
        
        # Add presigned URLs
        for audio in audios:
            audio["presigned_url"] = self.storage.generate_url(audio["storage_key"])
        
        return audios
    
    def get_collection_audios(
        self, collection_id: int, offset: int = 0, limit: int = 50
    ) -> List[Dict]:
        """
        Get collection audios with presigned URLs, sorted by subtopic number.
        
        Args:
            collection_id: Collection ID
            offset: Pagination offset
            limit: Maximum audios to return
        
        Returns:
            List of audio dicts sorted by subtopic number
        """
        audios = self.repository.get_collection_audios(collection_id, offset, limit)
        
        # Add presigned URLs
        for audio in audios:
            audio["presigned_url"] = self.storage.generate_url(audio["storage_key"])
        
        # Sort by subtopic number
        sorted_audios = sorted(audios, key=self._extract_subtopic_number)
        
        # Apply pagination after sorting
        if limit and limit > 0:
            return sorted_audios[offset:offset + limit]
        return sorted_audios[offset:]
    
    def delete_audio(self, audio_id: int, user_id: int) -> bool:
        """
        Delete audio from storage and database.
        
        Args:
            audio_id: audio ID
            user_id: User ID (for authorization)
        
        Returns:
            True if deleted, False if not found
        """
        # Get audio to find storage key
        audio = self.repository.get_audio_by_id(audio_id, user_id)
        if not audio:
            return False
        
        # Delete from storage
        self.storage.delete(audio["storage_key"])
        
        # Delete from database
        return self.repository.delete_audio(audio_id, user_id)
    
    def get_storage_stats(self) -> Dict:
        """
        Get storage statistics.
        
        Returns:
            Dict with storage backend stats
        """
        return self.storage.get_stats()
    
    @staticmethod
    def _extract_subtopic_number(audio: Dict) -> int:
        """Extract subtopic number from audio description or title."""
        description = audio.get('description', '')
        if description:
            match = re.search(r'Subtopic\s*(\d+)/\d+', description, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        title = audio.get('title', '')
        if title:
            match = re.search(r'subtopic[_\s]?(\d+)', title, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 999999  # Sort to end if no number found


# Convenience functions for backwards compatibility
def get_user_audios(user_id: int, offset: int = 0, limit: int = 5) -> List[Dict]:
    """Get user audios (backwards compatible function)."""
    service = audioService()
    return service.get_user_audios(user_id, offset, limit)


def get_collection_audios(collection_id: int, offset: int = 0, limit: int = 50) -> List[Dict]:
    """Get collection audios (backwards compatible function)."""
    service = audioService()
    return service.get_collection_audios(collection_id, offset, limit)



