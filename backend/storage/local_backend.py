"""Local filesystem storage backend for development."""
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Dict, Any, List, Iterator
from datetime import datetime

from .base import StorageBackend


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage implementation for development.
    
    Stores files in a local directory structure mirroring
    the S3 key structure (user_id/video_uuid.mp4).
    """
    
    def __init__(self, base_dir: str = "storage/videos"):
        """
        Initialize local storage backend.
        
        Args:
            base_dir: Base directory for storing files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        print(f"💾 Local Storage initialized: {self.base_dir.absolute()}")
    
    @property
    def backend_name(self) -> str:
        return f"Local ({self.base_dir})"
    
    def _get_path(self, key: str) -> Path:
        """Convert storage key to local file path."""
        return self.base_dir / key
    
    def upload(self, file_obj: BinaryIO, key: str, metadata: Dict[str, Any]) -> str:
        """Save file to local filesystem."""
        file_path = self._get_path(key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_obj.seek(0)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file_obj, f)
        
        return key
    
    def generate_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate file:// URL for local file.
        
        Note: expires_in is ignored for local storage as file:// URLs
        don't support expiration. A web server could be added later
        to serve files via HTTP with proper expiration.
        """
        file_path = self._get_path(key)
        return f"file://{file_path.absolute()}"

    def generate_background_urls(self) -> List[Dict[str, str]]:
        """List background videos under backgrounds/ with file:// URLs."""
        backgrounds_dir = self.base_dir / "backgrounds"
        if not backgrounds_dir.exists():
            return []

        items = []
        for file_path in sorted(backgrounds_dir.glob("*.mp4")):
            items.append({
                "id": file_path.stem,
                "url": f"file://{file_path.absolute()}",
            })
        return items

    def download(self, key: str, dest_path: str) -> str:
        """Copy an object to a local file path."""
        file_path = self._get_path(key)
        if not file_path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        shutil.copyfile(file_path, dest_path)
        return dest_path

    def iter_keys(self, prefix: str = "") -> Iterator[str]:
        """Yield all keys under a prefix."""
        search_path = self.base_dir / prefix if prefix else self.base_dir
        if not search_path.exists():
            return
        for file_path in search_path.rglob("*"):
            if file_path.is_file():
                yield str(file_path.relative_to(self.base_dir))

    def delete(self, key: str) -> bool:
        """Delete file from local filesystem."""
        file_path = self._get_path(key)
        try:
            file_path.unlink()
            # Clean up empty parent directories
            parent = file_path.parent
            if parent != self.base_dir and not any(parent.iterdir()):
                parent.rmdir()
            return True
        except FileNotFoundError:
            return False
    
    def exists(self, key: str) -> bool:
        """Check if file exists locally."""
        file_path = self._get_path(key)
        return file_path.exists()
    
    def get_size(self, key: str) -> int:
        """Get file size from local filesystem."""
        file_path = self._get_path(key)
        if not file_path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        return file_path.stat().st_size
    
    def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """List files in local storage."""
        files = []
        
        search_path = self.base_dir / prefix if prefix else self.base_dir
        if not search_path.exists():
            return files
        
        # Walk the directory tree
        for file_path in search_path.rglob("*"):
            if file_path.is_file() and len(files) < limit:
                # Calculate key relative to base_dir
                key = str(file_path.relative_to(self.base_dir))
                stat = file_path.stat()
                files.append({
                    "key": key,
                    "size": stat.st_size,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime),
                })
        
        return files
    
    def get_stats(self) -> Dict[str, Any]:
        """Get local storage statistics."""
        total_files = 0
        total_size = 0
        
        for file_path in self.base_dir.rglob("*"):
            if file_path.is_file():
                total_files += 1
                total_size += file_path.stat().st_size
        
        return {
            "backend": self.backend_name,
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_human": _format_size(total_size),
            "storage_path": str(self.base_dir.absolute()),
        }
