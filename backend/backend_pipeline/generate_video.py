#!/usr/bin/env python3
"""
Generate a single video from a dialogue transcript.

Usage:
    python backend_pipeline/generate_video.py \
        --transcript dialogue.json \
        --background assets/videos/minecraft.mp4 \
        --output assets/output/video.mp4
"""

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from services.video_service import VideoService
from services.collection_service import create_collection, get_collection

from backend_pipeline.audio_generation.minimax_tts import (
    generate_audio_from_transcript,
    concatenate_audio_segments,
)
from backend_pipeline.video_assembly.ffMpeg import (
    create_video_with_audio_and_captions,
)


def slugify(value: str) -> str:
    """Convert string to safe filename."""
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
    return safe[:64] or "dialogue"


def get_background_video(videos_dir: Path | str, video: Optional[str]) -> Path:
    """
    Randomly select a background video from the videos directory.
    If "video" provided then select a video that matches the name else select a random video
    Returns the path to the selected video.
    """
    videos_path = Path(videos_dir)
    
    if not videos_path.exists():
        raise FileNotFoundError(f"Background videos directory not found at {videos_dir}")
    
    # Get all .mp4 files from the videos directory
    video_files = list(videos_path.glob("*.mp4"))
    
    if not video_files or video_files == None:
        raise FileNotFoundError(f"No background videos found in {videos_dir}")

    if video:
        matching_videos = [f for f in video_files if video in f.name.lower()]
    else:
        matching_videos = []
        
    if matching_videos:
        selected_video = matching_videos[0]
    else:
        # Randomly select one video
        selected_video = random.choice(video_files)
    
    return selected_video


def load_dialogue(path: Path) -> Dict[str, Any]:
    """Load dialogue from JSON file."""
    with path.open("r") as f:
        data = json.load(f)

    # Support new format: {"dialogue_data": {"title": "...", "dialogue": [...]}}
    if "dialogue_data" in data:
        return data["dialogue_data"]
    
    # Support direct format: {"title": "...", "dialogue": [...]}
    if "title" in data and "dialogue" in data:
        return data
    
    raise ValueError("JSON must contain 'dialogue_data' or be a direct dialogue object with 'title' and 'dialogue'.")


def _build_educational_images_list(
    dialogue: list[Dict[str, Any]],
    audio_timings: list[Dict[str, Any]],
    image_dir: Optional[Path],
) -> list[Dict[str, Any]]:
    """
    Extract educational image configs from dialogue and calculate absolute timing.
    
    Supports both single image and multiple images per dialogue line:
    - "image": {...} - Single image (backward compatible)
    - "images": [{...}, {...}] - Multiple images displayed simultaneously
    
    Args:
        dialogue: List of dialogue lines with optional 'image' or 'images' field
        audio_timings: List of timing dicts with 'start' and 'end' for each line
        image_dir: Directory containing the educational images
    
    Returns:
        List of image configs with absolute timing:
        [
            {
                "path": "/path/to/image.png",
                "size": "small", "medium", or "large",
                "position": "top-right", "right-high", etc.,
                "start": 1.5,  # absolute start time
                "end": 4.2,    # absolute end time
            }
        ]
    """
    if not image_dir:
        return []
    
    educational_images = []
    
    for i, line in enumerate(dialogue):
        # Support both "images" array (new) and "image" (backward compatible)
        image_configs = []
        
        # Check for "images" array first (new format for simultaneous display)
        if "images" in line and isinstance(line["images"], list):
            image_configs = line["images"]
        # Fall back to single "image" (backward compatible)
        elif "image" in line and line["image"]:
            image_configs = [line["image"]]
        
        if not image_configs:
            continue
        
        # Skip if we don't have timing for this line
        if i >= len(audio_timings):
            print(f"⚠️  Warning: No timing for dialogue line {i}, skipping images")
            continue
        
        timing = audio_timings[i]
        line_start = timing["start"]
        line_end = timing["end"]
        
        # Process each image config
        for image_config in image_configs:
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
                "position": image_config.get("position"),  # Pass position to ffMpeg
                "start": absolute_start,
                "end": absolute_end,
            })
            
            size = image_config.get("size", "medium")
            position = image_config.get("position", "default")
            print(f"📷 Image '{filename}' scheduled: {absolute_start:.2f}s - {absolute_end:.2f}s ({size} @ {position})")
    
    return educational_images


def generate_video_from_dialogue(
    dialogue_data: Dict[str, Any],
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
    video: Optional[str] = None,
    collection_id: Optional[int] = None,
    image_dir: Optional[Path | str] = None,
    storage_backend: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    job_id: Optional[str] = None,
    karaoke_captions: bool = False,
) -> Dict[str, Any]:
    """
    Generate a single video from a dialogue transcript.

    Args:
        dialogue_data: Dictionary with 'title' and 'dialogue' keys
        background_video: Path to background video or directory of videos
        output_dir: Directory to store generated video
        audio_dir: Directory to store generated audio assets
        user_id: User ID for database entry
        collection_id: Optional existing collection ID. If not provided, creates new collection.
        image_dir: Optional directory containing educational images referenced in dialogue
        storage_backend: Storage backend override ('s3' or 'local'). Uses env var if not set.
        progress_callback: Optional callback function for progress updates.
                          Called with (job_id, current_stage, title)
        job_id: Job ID for progress tracking (required if progress_callback is provided)
        karaoke_captions: If True, use karaoke-style word-by-word highlighting instead of box captions

    Returns:
        Dictionary with video info including video_id, storage_key, collection_id
    """
    background_video_path = Path(background_video)
    output_dir = Path(output_dir)
    audio_dir = Path(audio_dir)
    image_dir_path = Path(image_dir) if image_dir else None

    print(f"\n{'='*60}")
    print(f"🔍 GENERATE_VIDEO_FROM_DIALOGUE - ENTRY")
    print(f"{'='*60}")
    print(f"  dialogue_data type: {type(dialogue_data)}")
    print(f"  dialogue_data keys: {dialogue_data.keys() if dialogue_data else 'None'}")

    title = dialogue_data.get("title", "Untitled Dialogue")
    print(f"  title: {title}")

    raw_dialogue = dialogue_data.get("dialogue")
    print(f"  raw dialogue type: {type(raw_dialogue)}")
    print(f"  raw dialogue is None: {raw_dialogue is None}")

    dialogue = raw_dialogue or []
    print(f"  dialogue length: {len(dialogue) if dialogue else 0}")

    if not dialogue:
        raise ValueError("No dialogue found in transcript.")

    # Log first few dialogue lines
    for i, line in enumerate(dialogue[:3]):
        print(f"  dialogue[{i}] keys: {line.keys() if isinstance(line, dict) else type(line)}")
        if isinstance(line, dict):
            print(f"    caption: {line.get('caption', 'MISSING')[:50] if line.get('caption') else 'None'}...")
            print(f"    speaker: {line.get('speaker', 'MISSING')}")
            print(f"    images: {line.get('images', 'None')}")
    print(f"{'='*60}\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Determine if background_video is a directory or a single file
    is_directory = background_video_path.is_dir()

    # === PROGRESS: Preparing assets ===
    if progress_callback and job_id:
        progress_callback(
            job_id=job_id,
            current_stage="preparing_assets",
            title=title,
        )
    
    # Select background video
    if is_directory:
            current_bg_video = get_background_video(background_video_path, video)
            print(f"Background video selected: {current_bg_video}")
    else:
        current_bg_video = background_video_path
    
    slug = slugify(title)
    print(f"\n=== Generating video: {title} ===")

    # Step 1: Create or use existing collection
    if collection_id is not None:
        # Use existing collection
        collection = get_collection(collection_id)
        collection_title = collection["collection_title"] if collection else "Collection"
        print(f"\n📁 Using existing collection: '{collection_title}' (ID: {collection_id})")
    else:
        # Create new collection
        collection_title = title
        collection_id = create_collection(user_id, collection_title)
        print(f"\n✨ Created collection: '{collection_title}' (ID: {collection_id})")

    # Step 2: Generate audio
    transcripts_payload = {"transcripts": dialogue}

    segment_dir = audio_dir / slug / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)

    # === PROGRESS: Audio generation ===
    if progress_callback and job_id:
        progress_callback(
            job_id=job_id,
            current_stage="audio_generation",
            title=title,
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
        dialogue=dialogue,
        audio_timings=audio_result["timings"],
        image_dir=image_dir_path,
    )

    # === PROGRESS: Video assembly ===
    if progress_callback and job_id:
        progress_callback(
            job_id=job_id,
            current_stage="video_assembly",
            title=title,
        )

    # Step 3: Create video
    video_output = output_dir / f"{slug}.mp4"
    caption_mode = "karaoke" if karaoke_captions else "box"
    print(f"🎥 Creating video… (caption mode: {caption_mode})")
    video_path = create_video_with_audio_and_captions(
        background_video=str(current_bg_video),
        audio_file=audio_result["audio_file"],
        caption_timings=audio_result["timings"],
        output_file=str(video_output),
        educational_images=educational_images,
        caption_mode=caption_mode,
    )

    # === PROGRESS: Uploading ===
    if progress_callback and job_id:
        progress_callback(
            job_id=job_id,
            current_stage="uploading",
            title=title,
        )

    # Step 4: Upload to storage and save to database
    video_service = VideoService(storage_backend=storage_backend)
    storage_name = video_service.storage.backend_name
    print(f"\n☁️  Uploading video to {storage_name}...")
    
    with open(video_output, "rb") as video_file:
        result = video_service.save_video(
            user_id=user_id,
            file_obj=video_file,
            original_filename=video_output.name,
            title=title,
            description=f"Generated from dialogue: {title}",
            collection_id=collection_id,
        )

    print(f"✅ Uploaded video_id {result['video_id']} for '{title}'")
    print(f"\n🎉 Video generation complete!")
    
    return {
        "title": title,
        "video_path": str(video_output),
        "audio_file": audio_result["audio_file"],
        "video_id": result["video_id"],
        "collection_id": collection_id,
        "storage_key": result["storage_key"],
        "access_url": result["access_url"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate video from dialogue transcript.")
    parser.add_argument(
        "--transcript",
        type=Path,
        required=True,
        help="Path to JSON file with dialogue_data output.",
    )
    parser.add_argument(
        "--background",
        type=Path,
        required=True,
        help="Background video path or directory (e.g., assets/videos/minecraft.mp4).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/output"),
        help="Directory to store generated video.",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path("assets/audio/generated"),
        help="Directory to store generated audio assets.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="User ID for database entry.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.transcript.exists():
        raise FileNotFoundError(f"Transcript file not found: {args.transcript}")
    if not args.background.exists():
        raise FileNotFoundError(f"Background video not found: {args.background}")

    dialogue_data = load_dialogue(args.transcript)
    
    result = generate_video_from_dialogue(
        dialogue_data=dialogue_data,
        background_video=args.background,
        output_dir=args.output_dir,
        audio_dir=args.audio_dir,
        user_id=args.user_id,
    )

    print("\n=== Summary ===")
    print(f"Title: {result['title']}")
    print(f"Video: {result['video_path']}")
    print(f"Collection ID: {result['collection_id']}")
    print(f"Video ID: {result['video_id']}")


if __name__ == "__main__":
    main()
