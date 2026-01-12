"""Abstract base class for storage backends."""
from abc import ABC, abstractmethod
from typing import BinaryIO, Dict, Any, List


class StorageBackend(ABC):
    """Abstract interface for video storage backends.
    
    All storage backends must implement these methods to ensure
    consistent behavior across S3, local filesystem, and any
    future storage providers.
    """
    
    @abstractmethod
    def upload(self, file_obj: BinaryIO, key: str, metadata: Dict[str, Any]) -> str:
        """
        Upload file to storage.
        
        Args:
            file_obj: Binary file object to upload
            key: Storage key/path for the file (e.g., "user_1/video_123.mp4")
            metadata: Additional metadata (content_type, etc.)
        
        Returns:
            Storage key where file was saved
        """
        pass
    
    @abstractmethod
    def generate_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate temporary access URL for file.
        
        Args:
            key: Storage key of the file
            expires_in: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            Temporary access URL (presigned URL for S3, file:// for local)
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete file from storage.
        
        Args:
            key: Storage key of file to delete
        
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if file exists in storage.
        
        Args:
            key: Storage key to check
        
        Returns:
            True if exists, False otherwise
        """
        pass
    
    @abstractmethod
    def get_size(self, key: str) -> int:
        """
        Get file size in bytes.
        
        Args:
            key: Storage key
        
        Returns:
            File size in bytes
        
        Raises:
            FileNotFoundError: If key doesn't exist
        """
        pass
    
    @abstractmethod
    def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """
        List files in storage.
        
        Args:
            prefix: Filter files by prefix (e.g., "user_1/")
            limit: Maximum number of files to return
        
        Returns:
            List of dicts with 'key', 'size', 'last_modified'
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dict with 'total_files', 'total_size_bytes', 'total_size_human'
        """
        pass
    
    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Return human-readable backend name."""
        pass
