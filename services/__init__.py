"""Services layer for business logic and data access.

This package contains:
- video_service: High-level video operations (storage + database)
- collection_service: Collection management
- account_service: User account management
- repositories/: Low-level database access layer
"""
from .video_service import VideoService, get_user_videos, get_collection_videos
from .collection_service import (
    create_collection,
    get_collection,
    get_user_collections,
    find_last_collection,
    generate_collection_title,
)
from . import account_service

__all__ = [
    # Video service
    "VideoService",
    "get_user_videos",
    "get_collection_videos",
    # Collection service
    "create_collection",
    "get_collection",
    "get_user_collections",
    "find_last_collection",
    "generate_collection_title",
    # Account service module
    "account_service",
]
