#!/usr/bin/env python3
"""
Generate one video per subtopic transcript chunk.

Usage:
    python backend_pipeline/generate_subtopic_videos.py \
        --transcripts assets/subtopics.json \
        --background assets/videos/minecraft.mp4 \
        --output-dir assets/output/subtopics
"""

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List
from save_to_db.save_video import add_video
from save_to_db.collection_service import create_collection, generate_collection_title

from backend_pipeline.audio_generation.elevenLabs import (
    generate_audio_from_transcript,
    concatenate_audio_segments,
)
from backend_pipeline.video_assembly.ffMpeg import (
    create_video_with_audio_and_captions,
)


def slugify(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return safe[:64] or "subtopic"


def get_random_background_video(videos_dir: Path | str) -> Path:
    """
    Randomly select a background video from the videos directory.
    Returns the path to the selected video.
    """
    videos_path = Path(videos_dir)
    
    if not videos_path.exists():
        raise FileNotFoundError(f"Background videos directory not found at {videos_dir}")
    
    # Get all .mp4 files from the videos directory
    video_files = list(videos_path.glob("*.mp4"))
    
    if not video_files:
        raise FileNotFoundError(f"No background videos found in {videos_dir}")
    
    # Randomly select one video
    selected_video = random.choice(video_files)
    
    return selected_video


def load_subtopics(path: Path) -> List[Dict[str, Any]]:
    with path.open("r") as f:
        data = json.load(f)

    if "subtopic_transcripts" in data:
        return data["subtopic_transcripts"]
    if "transcripts" in data:
        # Treat flat transcripts as single subtopic
        return [{"subtopic_title": "subtopic_1", "dialogue": data["transcripts"]}]
    raise ValueError("JSON must contain 'subtopic_transcripts' or 'transcripts'.")


def generate_videos_from_subtopic_list(
    subtopics: List[Dict[str, Any]],
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
) -> List[Dict[str, str]]:
    background_video_path = Path(background_video)
    output_dir = Path(output_dir)
    audio_dir = Path(audio_dir)

    if not subtopics:
        raise ValueError("No subtopics found in transcript file.")

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Determine if background_video is a directory or a single file
    is_directory = background_video_path.is_dir()

    # Step 1: Create collection first based on subtopic titles
    subtopic_titles = [subtopic["subtopic_title"] for subtopic in subtopics]
    collection_title = generate_collection_title(subtopic_titles)
    collection_id = create_collection(user_id, collection_title)

    print(f"\n✨ Created collection: '{collection_title}' (ID: {collection_id})")

    # Step 2: Generate all videos and store them temporarily
    video_files = []
    results = []
    
    for index, subtopic in enumerate(subtopics, start=1):
        # Select background video for this subtopic
        if is_directory:
            current_bg_video = get_random_background_video(background_video_path)
            print(f"🎥 Selected background: {current_bg_video.name}")
        else:
            current_bg_video = background_video_path
        slug = slugify(subtopic["subtopic_title"])
        print(f"\n=== Subtopic {index}/{len(subtopics)}: {subtopic['subtopic_title']} ===")

        transcripts_payload = {"transcripts": subtopic["dialogue"]}

        segment_dir = audio_dir / slug / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)

        print("🎙️  Generating audio segments…")
        audio_segments = generate_audio_from_transcript(
            transcripts_payload,
            output_dir=str(segment_dir),
        )

        audio_output = audio_dir / f"{slug}_full.mp3"
        print("🔗 Concatenating audio segments…")
        audio_result = concatenate_audio_segments(
            audio_segments,
            output_file=str(audio_output),
        )

        video_output = output_dir / f"{slug}.mp4"
        print("🎥 Creating video…")
        video_path = create_video_with_audio_and_captions(
            background_video=str(current_bg_video),
            audio_file=audio_result["audio_file"],
            caption_timings=audio_result["timings"],
            output_file=str(video_output),
        )
        
        # Store video file info for batch upload
        video_files.append({
            "path": video_output,
            "subtopic_title": subtopic["subtopic_title"],
            "index": index,
            "audio_file": audio_result["audio_file"],
        })

    # Step 3: Upload all videos to S3 and save to database with collection_id
    print(f"\n☁️  Uploading {len(video_files)} videos to S3 and database...")
    
    for video_info in video_files:
        with open(video_info["path"], "rb") as video_file:
            video_id = add_video(
                user_id=user_id,
                file_obj=video_file,
                original_filename=video_info["path"].name,
                title=video_info["subtopic_title"],
                description=f"Subtopic {video_info['index']}/{len(subtopics)}",
                collection_id=collection_id,
            )

        results.append(
            {
                "subtopic_title": video_info["subtopic_title"],
                "video_path": str(video_info["path"]),
                "audio_file": video_info["audio_file"],
                "video_id": video_id,
                "collection_id": collection_id,
            }
        )
        print(f"✅ Uploaded video_id {video_id} for '{video_info['subtopic_title']}'")

    print(f"\n🎉 All {len(results)} videos uploaded to collection '{collection_title}'")
    return results


def generate_videos_for_subtopics(
    transcripts_path: Path,
    background_video: Path,
    output_dir: Path,
    audio_dir: Path,
    user_id: int,
) -> List[Dict[str, str]]:
    subtopics = load_subtopics(transcripts_path)
    return generate_videos_from_subtopic_list(
        subtopics=subtopics,
        background_video=background_video,
        output_dir=output_dir,
        audio_dir=audio_dir,
        user_id=user_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate per-subtopic videos.")
    parser.add_argument(
        "--transcripts",
        type=Path,
        required=True,
        help="Path to JSON file with subtopic_transcripts output.",
    )
    parser.add_argument(
        "--background",
        type=Path,
        required=True,
        help="Background video path (e.g., assets/videos/minecraft.mp4).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/output/subtopics"),
        help="Directory to store generated videos.",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path("assets/audio/subtopics"),
        help="Directory to store generated audio assets.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.transcripts.exists():
        raise FileNotFoundError(f"Transcript file not found: {args.transcripts}")
    if not args.background.exists():
        raise FileNotFoundError(f"Background video not found: {args.background}")

    user_id = 1
    results = generate_videos_for_subtopics(
        transcripts_path=args.transcripts,
        background_video=args.background,
        output_dir=args.output_dir,
        audio_dir=args.audio_dir,
        user_id=user_id,
    )

    print("\n=== Summary ===")
    for item in results:
        print(f"- {item['subtopic_title']}: {item['video_path']} (Collection: {item['collection_id']})")


if __name__ == "__main__":
    main()
