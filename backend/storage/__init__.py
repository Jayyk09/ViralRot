"""Storage abstraction layer for video files.

Supports multiple storage backends:
- R2: Cloudflare R2 storage for production
- Local: Local filesystem storage for development

Usage:
    from storage import get_storage_backend
    
    storage = get_storage_backend()
    storage.upload(file_obj, "user_1/video.mp4", {"content_type": "video/mp4"})
    url = storage.generate_url("user_1/video.mp4")
"""
from .factory import get_storage_backend
from .base import StorageBackend

__all__ = ["get_storage_backend", "StorageBackend"]
