"""Factory for creating storage backend instances."""
import os
from typing import Optional

from .base import StorageBackend
from .r2_backend import R2StorageBackend
from .local_backend import LocalStorageBackend

# Project artifacts and reusable pipeline assets may live in separate buckets.
_storage_instance: Optional[StorageBackend] = None
_background_storage_instance: Optional[StorageBackend] = None


def get_storage_backend(
    backend_type: Optional[str] = None,
    force_new: bool = False
) -> StorageBackend:
    """
    Get configured storage backend (singleton pattern).

    Args:
        backend_type: Override backend type ('r2' or 'local').
                      If None, uses STORAGE_BACKEND env var.
        force_new: Force creation of new instance (for testing or CLI override)

    Returns:
        Configured StorageBackend instance

    Environment Variables:
        STORAGE_BACKEND: 'r2' or 'local' (default: 'r2')
        R2_ACCOUNT_ID: Cloudflare account ID
        R2_ACCESS_KEY_ID: R2 API token access key ID
        R2_SECRET_ACCESS_KEY: R2 API token secret access key
        R2_PROJECT_MEDIA_BUCKET_NAME: Project artifact bucket name
        LOCAL_STORAGE_DIR: Local storage directory (default: 'storage/videos')

    Examples:
        # Use default from environment
        storage = get_storage_backend()

        # Force local storage for development
        storage = get_storage_backend(backend_type="local", force_new=True)

        # Force R2 storage
        storage = get_storage_backend(backend_type="r2", force_new=True)
    """
    global _storage_instance

    # Use cached instance if available and not forcing new
    if _storage_instance is not None and not force_new and backend_type is None:
        return _storage_instance

    # Determine backend type
    if backend_type is None:
        backend_type = os.getenv("STORAGE_BACKEND", "r2").lower()
    else:
        backend_type = backend_type.lower()

    # Create appropriate backend
    if backend_type == "r2":
        required = {
            "R2_ACCOUNT_ID": os.getenv("R2_ACCOUNT_ID"),
            "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID"),
            "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY"),
            "R2_PROJECT_MEDIA_BUCKET_NAME": os.getenv("R2_PROJECT_MEDIA_BUCKET_NAME"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                f"R2 storage backend requires environment variables: {', '.join(missing)}"
            )
        instance = R2StorageBackend(
            bucket_name=required["R2_PROJECT_MEDIA_BUCKET_NAME"],
            account_id=required["R2_ACCOUNT_ID"],
            access_key_id=required["R2_ACCESS_KEY_ID"],
            secret_access_key=required["R2_SECRET_ACCESS_KEY"],
        )

    elif backend_type == "local":
        base_dir = os.getenv("LOCAL_STORAGE_DIR", "storage/videos")
        instance = LocalStorageBackend(base_dir)

    else:
        raise ValueError(
            f"Unknown storage backend: '{backend_type}'. "
            f"Valid options: 'r2', 'local'"
        )

    # Cache instance if using default (from environment)
    if not force_new:
        _storage_instance = instance

    return instance


def get_background_storage_backend(force_new: bool = False) -> StorageBackend:
    """Return the dedicated reusable-background asset storage backend.

    R2_BACKGROUND_BUCKET_NAME stores reusable source clips, while
    R2_PROJECT_MEDIA_BUCKET_NAME stores user projects, audio, overlays, and
    generated exports.
    """
    global _background_storage_instance
    if _background_storage_instance is not None and not force_new:
        return _background_storage_instance

    backend_type = os.getenv("STORAGE_BACKEND", "r2").lower()
    if backend_type == "r2":
        required = {
            "R2_ACCOUNT_ID": os.getenv("R2_ACCOUNT_ID"),
            "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID"),
            "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY"),
            "R2_BACKGROUND_BUCKET_NAME": os.getenv("R2_BACKGROUND_BUCKET_NAME"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "R2 background storage requires environment variables: "
                + ", ".join(missing)
            )
        if required["R2_BACKGROUND_BUCKET_NAME"] == os.getenv(
            "R2_PROJECT_MEDIA_BUCKET_NAME"
        ):
            raise ValueError("Background and project-media R2 buckets must be different")
        instance: StorageBackend = R2StorageBackend(
            bucket_name=required["R2_BACKGROUND_BUCKET_NAME"],
            account_id=required["R2_ACCOUNT_ID"],
            access_key_id=required["R2_ACCESS_KEY_ID"],
            secret_access_key=required["R2_SECRET_ACCESS_KEY"],
        )
    elif backend_type == "local":
        base_dir = os.getenv("LOCAL_BACKGROUND_STORAGE_DIR") or os.getenv(
            "LOCAL_STORAGE_DIR", "storage/videos"
        )
        instance = LocalStorageBackend(base_dir)
    else:
        raise ValueError(f"Unknown storage backend: '{backend_type}'")

    if not force_new:
        _background_storage_instance = instance
    return instance


def reset_storage_backend():
    """Reset cached project and background storage backends (for testing)."""
    global _storage_instance, _background_storage_instance
    _storage_instance = None
    _background_storage_instance = None
