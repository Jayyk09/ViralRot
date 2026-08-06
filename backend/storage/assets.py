"""Fetch pipeline assets (background videos, character images) from storage.

Assets live in the storage bucket (backgrounds/, assets/...) so the video
pipeline can run anywhere. Downloads are cached in a local directory keyed
by storage key, so repeated renders don't re-fetch.
"""
import os
from pathlib import Path
from typing import List

from .factory import get_background_storage_backend

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "tmp" / "asset_cache"


def _cache_dir() -> Path:
    return Path(os.getenv("ASSET_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))


def get_asset(key: str) -> Path:
    """
    Return a local path for a storage asset, downloading it if not cached.

    Args:
        key: Storage key (e.g., "backgrounds/minecraft.mp4")

    Returns:
        Path to the cached local file

    Raises:
        FileNotFoundError: If the key doesn't exist in storage
    """
    cached = _cache_dir() / key
    if cached.exists() and cached.stat().st_size > 0:
        return cached

    cached.parent.mkdir(parents=True, exist_ok=True)
    storage = get_background_storage_backend()

    # Download to a temp name, then rename, so a failed download
    # never leaves a truncated file in the cache
    partial = cached.with_suffix(cached.suffix + ".partial")
    try:
        storage.download(key, str(partial))
    except Exception as e:
        partial.unlink(missing_ok=True)
        raise FileNotFoundError(f"Asset not found in storage: {key}") from e
    partial.rename(cached)

    print(f"⬇️  Fetched asset from {storage.backend_name}: {key}")
    return cached


def list_asset_keys(prefix: str) -> List[str]:
    """List all storage keys under a prefix."""
    storage = get_background_storage_backend()
    return list(storage.iter_keys(prefix))
