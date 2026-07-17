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
from typing import Any, Callable, Dict, List, Optional
from services.video_service import VideoService
from services.collection_service import create_collection, generate_collection_title, get_collection

from backend_pipeline.audio_generation.minimax_tts import (
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


def _build_educational_images_list(
    dialogue: List[Dict[str, Any]],
    audio_timings: List[Dict[str, Any]],
    image_dir: Optional[Path],
) -> List[Dict[str, Any]]:
    """
    Extract educational image configs from dialogue and calculate absolute timing.
    
    Args:
        dialogue: List of dialogue lines with optional 'image' field
        audio_timings: List of timing dicts with 'start' and 'end' for each line
        image_dir: Directory containing the educational images
    
    Returns:
        List of image configs with absolute timing:
        [
            {
                "path": "/path/to/image.png",
                "size": "medium" or "large",
                "start": 1.5,  # absolute start time
                "end": 4.2,    # absolute end time
            }
        ]
    """
    if not image_dir:
        return []
    
    educational_images = []
    
    for i, line in enumerate(dialogue):
        image_config = line.get("image")
        if not image_config:
            continue
        
        # Skip if we don't have timing for this line
        if i >= len(audio_timings):
            print(f"⚠️  Warning: No timing for dialogue line {i}, skipping image")
            continue
        
        timing = audio_timings[i]
        line_start = timing["start"]
        line_end = timing["end"]
        line_duration = line_end - line_start
        
        # Build image path
        filename = image_config.get("filename")
        if not filename:
            continue
        
        image_path = image_dir / filename
        if not image_path.exists():
            print(f"⚠️  Warning: Image not found: {image_path}")
            continue
        
        # Calculate timing
        # start_time: offset from line start (default 0)
        # duration: how long to show (default: entire line)
        custom_start = image_config.get("start_time", 0) or 0
        custom_duration = image_config.get("duration")
        
        absolute_start = line_start + custom_start
        
        if custom_duration:
            absolute_end = min(absolute_start + custom_duration, line_end)
        else:
            absolute_end = line_end
        
        educational_images.append({
            "path": str(image_path),
            "size": image_config.get("size", "medium"),
            "start": absolute_start,
            "end": absolute_end,
        })
        
        print(f"📷 Image '{filename}' scheduled: {absolute_start:.2f}s - {absolute_end:.2f}s ({image_config.get('size', 'medium')})")
    
    return educational_images


def generate_videos_from_subtopic_list(
    subtopics: List[Dict[str, Any]],
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
    collection_id: Optional[int] = None,
    image_dir: Optional[Path | str] = None,
    storage_backend: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    job_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Generate videos from a list of subtopic transcripts.

    Args:
        subtopics: List of subtopic dictionaries with dialogue
        background_video: Path to background video or directory of videos
        output_dir: Directory to store generated videos
        audio_dir: Directory to store generated audio assets
        user_id: User ID for database entry
        collection_id: Optional existing collection ID. If not provided, creates new collection.
        image_dir: Optional directory containing educational images referenced in dialogue
        storage_backend: Storage backend override ('r2' or 'local'). Uses env var if not set.
        progress_callback: Optional callback function for progress updates.
                          Called with (job_id, current_stage, current_subtopic, subtopic_title)
        job_id: Job ID for progress tracking (required if progress_callback is provided)

    Returns:
        List of dictionaries with video info for each subtopic
    """
    background_video_path = Path(background_video)
    output_dir = Path(output_dir)
    audio_dir = Path(audio_dir)
    image_dir_path = Path(image_dir) if image_dir else None

    if not subtopics:
        raise ValueError("No subtopics found in transcript file.")

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Determine if background_video is a directory or a single file
    is_directory = background_video_path.is_dir()

    # Step 1: Create or use existing collection
    subtopic_titles = [subtopic["subtopic_title"] for subtopic in subtopics]

    if collection_id is not None:
        # Use existing collection
        collection = get_collection(collection_id)
        collection_title = collection["collection_title"] if collection else "Collection"
        print(f"\n📁 Using existing collection: '{collection_title}' (ID: {collection_id})")
    else:
        # Create new collection
        collection_title = generate_collection_title(subtopic_titles)
        collection_id = create_collection(user_id, collection_title)
        print(f"\n✨ Created collection: '{collection_title}' (ID: {collection_id})")

    # Step 2: Generate all videos and store them temporarily
    video_files = []
    results = []
    
    for index, subtopic in enumerate(subtopics, start=1):
        subtopic_title = subtopic["subtopic_title"]
        
        # === PROGRESS: Preparing assets ===
        if progress_callback and job_id:
            progress_callback(
                job_id=job_id,
                current_stage="preparing_assets",
                current_subtopic=index,
                subtopic_title=subtopic_title,
            )
        
        # Select background video for this subtopic
        if is_directory:
            current_bg_video = get_random_background_video(background_video_path)
            print(f"🎥 Selected background: {current_bg_video.name}")
        else:
            current_bg_video = background_video_path
        slug = slugify(subtopic_title)
        print(f"\n=== Subtopic {index}/{len(subtopics)}: {subtopic_title} ===")

        transcripts_payload = {"transcripts": subtopic["dialogue"]}

        segment_dir = audio_dir / slug / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)

        # === PROGRESS: Audio generation ===
        if progress_callback and job_id:
            progress_callback(
                job_id=job_id,
                current_stage="audio_generation",
                current_subtopic=index,
                subtopic_title=subtopic_title,
            )
        
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

        # Build educational images list if image_dir is provided
        educational_images = _build_educational_images_list(
            dialogue=subtopic["dialogue"],
            audio_timings=audio_result["timings"],
            image_dir=image_dir_path,
        )

        # === PROGRESS: Video assembly ===
        if progress_callback and job_id:
            progress_callback(
                job_id=job_id,
                current_stage="video_assembly",
                current_subtopic=index,
                subtopic_title=subtopic_title,
            )

        video_output = output_dir / f"{slug}.mp4"
        print("🎥 Creating video…")
        video_path = create_video_with_audio_and_captions(
            background_video=str(current_bg_video),
            audio_file=audio_result["audio_file"],
            caption_timings=audio_result["timings"],
            output_file=str(video_output),
            educational_images=educational_images,
        )
        
        # Store video file info for batch upload
        video_files.append({
            "path": video_output,
            "subtopic_title": subtopic_title,
            "index": index,
            "audio_file": audio_result["audio_file"],
        })

    # Step 3: Upload all videos to storage and save to database with collection_id
    video_service = VideoService(storage_backend=storage_backend)
    storage_name = video_service.storage.backend_name
    print(f"\n☁️  Uploading {len(video_files)} videos to {storage_name}...")
    
    for video_info in video_files:
        # === PROGRESS: Uploading ===
        if progress_callback and job_id:
            progress_callback(
                job_id=job_id,
                current_stage="uploading",
                current_subtopic=video_info["index"],
                subtopic_title=video_info["subtopic_title"],
            )
        
        with open(video_info["path"], "rb") as video_file:
            result = video_service.save_video(
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
                "video_id": result["video_id"],
                "collection_id": collection_id,
                "storage_key": result["storage_key"],
            }
        )
        print(f"✅ Uploaded video_id {result['video_id']} for '{video_info['subtopic_title']}'")

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
