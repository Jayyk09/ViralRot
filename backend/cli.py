#!/usr/bin/env python3
"""
CLI for video generation pipeline.

Generate a single educational video from a source.

Usage:
    python cli.py --source lecture.mp3 --source-type audio --user-id 1
    python cli.py --source notes.txt --source-type text
    python cli.py --source "https://youtube.com/watch?v=..." --source-type youtube
    python cli.py --source slides.pptx --source-type pptx
    
    # Use local storage for development
    python cli.py --source "test content" --source-type text --storage local
    
    # Show storage statistics
    python cli.py --storage-stats
"""

import argparse
import os
from pathlib import Path
from uuid import uuid4

from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_video import generate_video_from_dialogue
from services.collection_service import create_collection
from services.video_service import VideoService


def generate_complete_collection(
    source: str,
    source_type: str,
    user_id: int,
    background_dir: Path,
    output_dir: Path,
    audio_dir: Path,
    storage_backend: str | None = None,
) -> dict:
    """
    Generate a single video from source material.

    Args:
        source: File path, text content, or YouTube URL
        source_type: One of 'audio', 'text', 'youtube', 'pptx'
        user_id: User ID for database entries
        background_dir: Directory containing background videos (or single video file)
        output_dir: Base directory for output videos
        audio_dir: Base directory for generated audio
        storage_backend: Storage backend ('s3' or 'local'). Uses env var if not set.

    Returns:
        Dictionary with collection info and video result
    """
    session_id = uuid4().hex

    # Normalize source type
    if source_type == "audio":
        source_type = "audio/mp3"

    # Show storage backend info
    video_service = VideoService(storage_backend=storage_backend)
    storage_name = video_service.storage.backend_name

    print(f"\n{'='*60}")
    print(f"Starting video generation pipeline")
    print(f"Source: {source[:100]}{'...' if len(source) > 100 else ''}")
    print(f"Type: {source_type}")
    print(f"Storage: {storage_name}")
    print(f"Session: {session_id}")
    print(f"{'='*60}\n")

    # Step 1: Extract dialogue transcript
    print("📝 Step 1: Extracting dialogue transcript...")
    dialogue = extract_transcripts(source, source_type)

    if not dialogue or not dialogue.dialogue:
        raise ValueError("No dialogue extracted from source material")

    print(f"   Title: '{dialogue.title}'")
    print(f"   Exchanges: {len(dialogue.dialogue)}")

    # Step 2: Create collection
    print("\n📁 Step 2: Creating collection...")
    collection_id = create_collection(user_id, dialogue.title)
    print(f"   Collection: '{dialogue.title}' (ID: {collection_id})")

    # Step 3: Generate video
    print("\n🎬 Step 3: Generating video...")
    video_output_dir = output_dir / f"collection_{session_id}"
    video_audio_dir = audio_dir / f"collection_{session_id}"

    def progress_callback(stage: str):
        print(f"   {stage}")

    video_result = generate_video_from_dialogue(
        dialogue_data=dialogue.model_dump(),
        background_video=background_dir,
        output_dir=video_output_dir,
        audio_dir=video_audio_dir,
        user_id=user_id,
        collection_id=collection_id,
        storage_backend=storage_backend,
        progress_callback=lambda stage: progress_callback(stage),
    )

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")

    return {
        "collection_id": collection_id,
        "collection_title": dialogue.title,
        "video_id": video_result["video_id"],
        "video_url": video_result.get("video_url"),
        "session_id": session_id,
        "storage_backend": storage_name,
    }


def show_storage_stats(storage_backend: str | None = None):
    """Display storage statistics."""
    video_service = VideoService(storage_backend=storage_backend)
    stats = video_service.get_storage_stats()
    
    print(f"\n{'='*60}")
    print("Storage Statistics")
    print(f"{'='*60}")
    print(f"Backend: {stats['backend']}")
    print(f"Total Files: {stats['total_files']}")
    print(f"Total Size: {stats['total_size_human']}")
    if 'storage_path' in stats:
        print(f"Storage Path: {stats['storage_path']}")
    print(f"{'='*60}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate complete video collection from source material.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py --source lecture.mp3 --source-type audio
  python cli.py --source notes.txt --source-type text
  python cli.py --source "https://youtube.com/watch?v=abc" --source-type youtube
  python cli.py --source slides.pptx --source-type pptx
  
  # Use local storage for development
  python cli.py --source "test content" --source-type text --storage local
  
  # Show storage statistics
  python cli.py --storage-stats
  python cli.py --storage-stats --storage local
        """,
    )
    parser.add_argument(
        "--source",
        help="Source file path, text content, or YouTube URL",
    )
    parser.add_argument(
        "--source-type",
        choices=["audio", "text", "youtube", "pptx"],
        help="Type of source material",
    )
    parser.add_argument(
        "--background",
        type=Path,
        default=Path("assets/videos"),
        help="Directory containing background videos (default: assets/videos)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/output"),
        help="Output directory for generated videos (default: assets/output)",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path("assets/audio/generated"),
        help="Output directory for generated audio (default: assets/audio/generated)",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="User ID for database entries (default: 1)",
    )
    parser.add_argument(
        "--storage",
        choices=["s3", "local"],
        help="Storage backend to use (default: from STORAGE_BACKEND env var or 's3')",
    )
    parser.add_argument(
        "--storage-stats",
        action="store_true",
        help="Show storage statistics and exit",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Handle storage stats command
    if args.storage_stats:
        show_storage_stats(args.storage)
        return

    # Require source and source-type for video generation
    if not args.source or not args.source_type:
        print("Error: --source and --source-type are required for video generation")
        print("Use --storage-stats to view storage statistics")
        return

    # Validate source exists for file-based inputs
    if args.source_type in ("audio", "pptx"):
        source_path = Path(args.source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {args.source}")
        source = str(source_path)
    elif args.source_type == "text":
        # Check if it's a file path or raw text
        source_path = Path(args.source)
        if source_path.exists():
            source = source_path.read_text()
        else:
            source = args.source
    else:
        source = args.source

    # Validate background directory
    if not args.background.exists():
        raise FileNotFoundError(f"Background videos directory not found: {args.background}")

    result = generate_complete_collection(
        source=source,
        source_type=args.source_type,
        user_id=args.user_id,
        background_dir=args.background,
        output_dir=args.output_dir,
        audio_dir=args.audio_dir,
        storage_backend=args.storage,
    )

    print("\n=== Summary ===")
    print(f"Collection ID: {result['collection_id']}")
    print(f"Collection Title: {result['collection_title']}")
    print(f"Video ID: {result['video_id']}")
    print(f"Storage Backend: {result['storage_backend']}")
    if result.get("video_url"):
        print(f"Video URL: {result['video_url']}")


if __name__ == "__main__":
    main()
