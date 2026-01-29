#!/usr/bin/env python3
"""
Cleanup Script: Delete all videos and collections from database and S3.

This script performs a complete cleanup of:
1. All videos from S3 storage
2. All videos from the database
3. All collections from the database

Usage:
    python scripts/cleanup_all_data.py              # Dry run (shows what would be deleted)
    python scripts/cleanup_all_data.py --execute   # Actually delete everything
    python scripts/cleanup_all_data.py --backup    # Export to JSON before deleting

WARNING: This is a destructive operation. Use --backup to save data first.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from db import get_db_conn
from storage import get_storage_backend


def get_all_videos() -> List[Dict[str, Any]]:
    """Get all videos from database."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, s3_key, video_title, video_description, collection_id, created_at
                FROM videos
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "storage_key": row[2],  # s3_key mapped to storage_key for consistency
                    "title": row[3],  # video_title mapped to title
                    "description": row[4],  # video_description mapped to description
                    "collection_id": row[5],
                    "created_at": row[6].isoformat() if row[6] else None,
                }
                for row in rows
            ]
    finally:
        conn.close()


def get_all_collections() -> List[Dict[str, Any]]:
    """Get all collections from database."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, collection_title, created_at
                FROM collections
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "collection_title": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]
    finally:
        conn.close()


def delete_video_from_s3(storage_key: str, storage) -> bool:
    """Delete a video from S3 storage."""
    try:
        storage.delete(storage_key)
        return True
    except Exception as e:
        print(f"    Warning: Failed to delete S3 key '{storage_key}': {e}")
        return False


def delete_all_videos_from_db() -> int:
    """Delete all videos from database. Returns count deleted."""
    conn = get_db_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM videos")
            return cur.rowcount
    finally:
        conn.close()


def delete_all_collections_from_db() -> int:
    """Delete all collections from database. Returns count deleted."""
    conn = get_db_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM collections")
            return cur.rowcount
    finally:
        conn.close()


def backup_to_json(videos: List[Dict], collections: List[Dict], backup_dir: Path) -> Path:
    """Export all data to JSON backup file."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"backup_{timestamp}.json"
    
    backup_data = {
        "exported_at": datetime.now().isoformat(),
        "video_count": len(videos),
        "collection_count": len(collections),
        "videos": videos,
        "collections": collections,
    }
    
    with open(backup_file, "w") as f:
        json.dump(backup_data, f, indent=2)
    
    return backup_file


def main():
    parser = argparse.ArgumentParser(
        description="Delete all videos and collections from database and S3"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the deletion (without this flag, only shows what would be deleted)"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create JSON backup before deleting"
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("backups"),
        help="Directory for backup files (default: ./backups)"
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    
    print("=" * 60)
    print("VIDEO AND COLLECTION CLEANUP SCRIPT")
    print("=" * 60)
    print()
    
    # Get current data
    print("Fetching current data...")
    videos = get_all_videos()
    collections = get_all_collections()
    
    print(f"  Found {len(videos)} videos")
    print(f"  Found {len(collections)} collections")
    print()
    
    if len(videos) == 0 and len(collections) == 0:
        print("Nothing to delete. Database is already clean.")
        return
    
    # Show what will be deleted
    print("VIDEOS TO DELETE:")
    print("-" * 40)
    for video in videos[:10]:  # Show first 10
        print(f"  ID: {video['id']}, Title: {video['title'][:40] if video['title'] else 'N/A'}...")
        print(f"      S3 Key: {video['storage_key']}")
    if len(videos) > 10:
        print(f"  ... and {len(videos) - 10} more")
    print()
    
    print("COLLECTIONS TO DELETE:")
    print("-" * 40)
    for collection in collections[:10]:  # Show first 10
        print(f"  ID: {collection['id']}, Title: {collection['collection_title'][:40] if collection['collection_title'] else 'N/A'}")
    if len(collections) > 10:
        print(f"  ... and {len(collections) - 10} more")
    print()
    
    if not args.execute:
        print("=" * 60)
        print("DRY RUN MODE - No changes made")
        print("To actually delete, run with --execute flag")
        print("To backup first, add --backup flag")
        print("=" * 60)
        return
    
    # Backup if requested
    if args.backup:
        print("Creating backup...")
        backup_file = backup_to_json(videos, collections, args.backup_dir)
        print(f"  Backup saved to: {backup_file}")
        print()
    
    # Initialize storage backend
    print("Initializing storage backend...")
    try:
        storage = get_storage_backend()
        print(f"  Using: {storage.backend_name}")
    except Exception as e:
        print(f"  Warning: Could not initialize storage backend: {e}")
        print("  Will only delete from database, S3 files will remain")
        storage = None
    print()
    
    # Delete from S3
    if storage and videos:
        print("Deleting videos from S3...")
        s3_deleted = 0
        s3_failed = 0
        for video in videos:
            if video['storage_key']:
                if delete_video_from_s3(video['storage_key'], storage):
                    s3_deleted += 1
                else:
                    s3_failed += 1
        print(f"  Deleted: {s3_deleted}")
        print(f"  Failed: {s3_failed}")
        print()
    
    # Delete from database
    print("Deleting videos from database...")
    videos_deleted = delete_all_videos_from_db()
    print(f"  Deleted: {videos_deleted} videos")
    print()
    
    print("Deleting collections from database...")
    collections_deleted = delete_all_collections_from_db()
    print(f"  Deleted: {collections_deleted} collections")
    print()
    
    print("=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)
    print(f"  Videos deleted from S3: {s3_deleted if storage else 'N/A'}")
    print(f"  Videos deleted from DB: {videos_deleted}")
    print(f"  Collections deleted from DB: {collections_deleted}")
    if args.backup:
        print(f"  Backup file: {backup_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
