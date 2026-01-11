#!/usr/bin/env python3
"""
CLI for video generation pipeline.

Generate subtopic videos from a single source.

Usage:
    python cli.py --source lecture.mp3 --source-type audio --user-id 1
    python cli.py --source notes.txt --source-type text
    python cli.py --source "https://youtube.com/watch?v=..." --source-type youtube
    python cli.py --source slides.pptx --source-type pptx
"""

import argparse
from pathlib import Path
from uuid import uuid4

from frontend_pipeline.script_generation.transcripts import extract_transcripts
from backend_pipeline.generate_subtopic_videos import generate_videos_from_subtopic_list
from save_to_db.collection_service import create_collection, generate_collection_title


def generate_complete_collection(
    source: str,
    source_type: str,
    user_id: int,
    background_dir: Path,
    output_dir: Path,
    audio_dir: Path,
) -> dict:
    """
    Generate a video collection from source material.

    Args:
        source: File path, text content, or YouTube URL
        source_type: One of 'audio', 'text', 'youtube', 'pptx'
        user_id: User ID for database entries
        background_dir: Directory containing background videos
        output_dir: Base directory for output videos
        audio_dir: Base directory for generated audio

    Returns:
        Dictionary with collection info and video results
    """
    session_id = uuid4().hex

    # Normalize source type
    if source_type == "audio":
        source_type = "audio/mp3"

    print(f"\n{'='*60}")
    print(f"Starting video generation pipeline")
    print(f"Source: {source[:100]}{'...' if len(source) > 100 else ''}")
    print(f"Type: {source_type}")
    print(f"Session: {session_id}")
    print(f"{'='*60}\n")

    # Step 1: Extract subtopic transcripts
    print("📝 Step 1: Extracting subtopic transcripts...")
    subtopics = extract_transcripts(source, source_type)

    if not subtopics:
        raise ValueError("No subtopics extracted from source material")

    print(f"   Found {len(subtopics)} subtopics")

    # Step 2: Create collection
    print("\n📁 Step 2: Creating collection...")
    subtopic_titles = [s.subtopic_title for s in subtopics]
    collection_title = generate_collection_title(subtopic_titles)
    collection_id = create_collection(user_id, collection_title)
    print(f"   Collection: '{collection_title}' (ID: {collection_id})")

    # Step 3: Generate subtopic videos
    print("\n🎬 Step 3: Generating subtopic videos...")
    subtopic_video_dir = output_dir / f"collection_{session_id}" / "subtopics"
    subtopic_audio_dir = audio_dir / f"collection_{session_id}" / "subtopics"

    subtopic_results = generate_videos_from_subtopic_list(
        subtopics=[s.model_dump() for s in subtopics],
        background_video=background_dir,
        output_dir=subtopic_video_dir,
        audio_dir=subtopic_audio_dir,
        user_id=user_id,
        collection_id=collection_id,
    )

    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")

    return {
        "collection_id": collection_id,
        "collection_title": collection_title,
        "subtopic_count": len(subtopic_results),
        "total_videos": len(subtopic_results),
        "subtopic_results": subtopic_results,
        "session_id": session_id,
    }


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
        """,
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source file path, text content, or YouTube URL",
    )
    parser.add_argument(
        "--source-type",
        required=True,
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
    return parser.parse_args()


def main():
    args = parse_args()

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
    )

    print("\n=== Summary ===")
    print(f"Collection ID: {result['collection_id']}")
    print(f"Collection Title: {result['collection_title']}")
    print(f"Total Videos: {result['total_videos']}")
    print(f"\nSubtopic Videos:")
    for item in result["subtopic_results"]:
        print(f"  - {item['subtopic_title']}: video_id={item['video_id']}")


if __name__ == "__main__":
    main()
