"""Factory for creating storage backend instances."""
import os
from typing import Optional

from .base import StorageBackend
from .s3_backend import S3StorageBackend
from .local_backend import LocalStorageBackend

# Singleton storage instance
_storage_instance: Optional[StorageBackend] = None


def get_storage_backend(
    backend_type: Optional[str] = None,
    force_new: bool = False
) -> StorageBackend:
    """
    Get configured storage backend (singleton pattern).
    
    Args:
        backend_type: Override backend type ('s3' or 'local'). 
                      If None, uses STORAGE_BACKEND env var.
        force_new: Force creation of new instance (for testing or CLI override)
    
    Returns:
        Configured StorageBackend instance
    
    Environment Variables:
        STORAGE_BACKEND: 's3' or 'local' (default: 's3')
        S3_BUCKET_NAME: S3 bucket name (default: 'emory-hacks-video-bucket')
        AWS_DEFAULT_REGION: AWS region (default: 'us-east-2')
        LOCAL_STORAGE_DIR: Local storage directory (default: 'storage/videos')
    
    Examples:
        # Use default from environment
        storage = get_storage_backend()
        
        # Force local storage for development
        storage = get_storage_backend(backend_type="local", force_new=True)
        
        # Force S3 storage
        storage = get_storage_backend(backend_type="s3", force_new=True)
    """
    global _storage_instance
    
    # Use cached instance if available and not forcing new
    if _storage_instance is not None and not force_new and backend_type is None:
        return _storage_instance
    
    # Determine backend type
    if backend_type is None:
        backend_type = os.getenv("STORAGE_BACKEND", "s3").lower()
    else:
        backend_type = backend_type.lower()
    
    # Create appropriate backend
    if backend_type == "s3":
        bucket = os.getenv("S3_BUCKET_NAME", "emory-hacks-video-bucket")
        region = os.getenv("AWS_DEFAULT_REGION", "us-east-2")
        instance = S3StorageBackend(bucket, region)
    
    elif backend_type == "local":
        base_dir = os.getenv("LOCAL_STORAGE_DIR", "storage/videos")
        instance = LocalStorageBackend(base_dir)
    
    else:
        raise ValueError(
            f"Unknown storage backend: '{backend_type}'. "
            f"Valid options: 's3', 'local'"
        )
    
    # Cache instance if using default (from environment)
    if not force_new:
        _storage_instance = instance
    
    return instance


def reset_storage_backend():
    """Reset cached storage backend (for testing)."""
    global _storage_instance
    _storage_instance = None
