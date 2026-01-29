#!/usr/bin/env python3
"""
CLI tool for testing image overlay in videos without running the full pipeline.

This tool allows you to test educational image overlays using existing audio files
and background videos, with mock caption timing based on audio duration.

Usage:
    python test_image_overlay.py --config test_config.json
    python test_image_overlay.py --config test_config.json --output custom_output.mp4
    python test_image_overlay.py --config test_config.json --verbose

Config file format (JSON):
{
  "audio_file": "assets/audio/generated/collection_xxx/dialogue_title.mp3",
  "background_video": "assets/videos/minecraft.mp4",
  "output_file": "tmp/test_videos/test_output.mp4",
  "dialogue": [
    {
      "caption": "Check out this diagram!",
      "speaker": "PETER",
      "emotion": "excited",
      "image": {
        "filename": "test_diagram.png",
        "size": "large",
        "start_time": 0.5,
        "duration": 3.0
      }
    },
    {
      "caption": "Fascinating! That explains everything.",
      "speaker": "STEWIE",
      "emotion": "neutral"
    }
  ],
  "images": {
    "test_diagram.png": "/absolute/path/to/test_diagram.png"
  }
}
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any

from backend_pipeline.video_assembly.ffMpeg import create_video_with_audio_and_captions


def get_audio_duration(audio_file: Path) -> float:
    """Get audio file duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_file)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get audio duration: {result.stderr}")
    
    if not result.stdout.strip():
        raise ValueError(f"Could not determine audio duration for {audio_file}")
    
    return float(result.stdout.strip())


def calculate_caption_timings(
    dialogue: List[Dict[str, Any]],
    total_duration: float
) -> List[Dict[str, Any]]:
    """
    Calculate mock caption timings based on dialogue length and audio duration.
    
    Distributes time proportionally based on caption word count,
    with small pauses between speaker exchanges.
    
    Args:
        dialogue: List of dialogue lines with caption, speaker, emotion
        total_duration: Total audio duration in seconds
    
    Returns:
        List of timing dicts with start, end, caption, speaker, emotion
    """
    if not dialogue:
        return []
    
    # Calculate word counts for each line
    word_counts = [len(line["caption"].split()) for line in dialogue]
    total_words = sum(word_counts)
    
    if total_words == 0:
        # Equal distribution if no words
        time_per_line = total_duration / len(dialogue)
        timings = []
        for i, line in enumerate(dialogue):
            start = i * time_per_line
            end = (i + 1) * time_per_line
            timings.append({
                "start": start,
                "end": end,
                "caption": line["caption"],
                "speaker": line["speaker"],
                "emotion": line.get("emotion", "neutral"),
            })
        return timings
    
    # Distribute time proportionally based on word count
    # Reserve 0.2s pause between speaker changes
    pause_duration = 0.2
    num_pauses = sum(
        1 for i in range(len(dialogue) - 1)
        if dialogue[i]["speaker"] != dialogue[i + 1]["speaker"]
    )
    
    total_pause_time = num_pauses * pause_duration
    available_time = total_duration - total_pause_time
    
    timings = []
    current_time = 0.0
    previous_speaker = None
    
    for i, line in enumerate(dialogue):
        # Add pause if speaker changed
        if previous_speaker and previous_speaker != line["speaker"]:
            current_time += pause_duration
        
        # Calculate duration for this line based on word count
        line_duration = (word_counts[i] / total_words) * available_time
        
        timings.append({
            "start": current_time,
            "end": current_time + line_duration,
            "caption": line["caption"],
            "speaker": line["speaker"],
            "emotion": line.get("emotion", "neutral"),
        })
        
        current_time += line_duration
        previous_speaker = line["speaker"]
    
    return timings


def build_educational_images_list(
    dialogue: List[Dict[str, Any]],
    caption_timings: List[Dict[str, Any]],
    image_paths: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Build educational images list with absolute timing from dialogue config.
    
    Supports both single image and multiple images per dialogue line:
    - "image": {...} - Single image (backward compatible)
    - "images": [{...}, {...}] - Multiple images displayed simultaneously
    
    Args:
        dialogue: Original dialogue config with image references
        caption_timings: Calculated timing data for each line
        image_paths: Mapping of filename to absolute path
    
    Returns:
        List of image configs for FFmpeg overlay
    """
    educational_images = []
    
    for i, line in enumerate(dialogue):
        # Support both "image" (single) and "images" (array) formats
        image_configs = []
        
        # Check for "images" array first (new format for simultaneous display)
        if "images" in line and isinstance(line["images"], list):
            image_configs = line["images"]
        # Fall back to single "image" (backward compatible)
        elif "image" in line and line["image"]:
            image_configs = [line["image"]]
        
        if not image_configs:
            continue
        
        # Get timing for this line
        if i >= len(caption_timings):
            print(f"⚠️  Warning: No timing for dialogue line {i}, skipping images")
            continue
        
        timing = caption_timings[i]
        line_start = timing["start"]
        line_end = timing["end"]
        
        # Process each image in the config (supports multiple simultaneous images)
        for image_config in image_configs:
            # Get image path
            filename = image_config.get("filename")
            if not filename or filename not in image_paths:
                print(f"⚠️  Warning: Image '{filename}' not found in image paths")
                continue
            
            image_path = Path(image_paths[filename])
            if not image_path.exists():
                print(f"⚠️  Warning: Image file not found: {image_path}")
                continue
            
            # Calculate absolute timing
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


def validate_config(config: Dict[str, Any]) -> None:
    """Validate config file structure and file paths."""
    # Check required fields
    required_fields = ["audio_file", "background_video", "dialogue"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required field in config: {field}")
    
    # Check audio file exists
    audio_file = Path(config["audio_file"])
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    
    # Check background video exists
    bg_video = Path(config["background_video"])
    if not bg_video.exists():
        raise FileNotFoundError(f"Background video not found: {bg_video}")
    
    # Check dialogue structure
    if not isinstance(config["dialogue"], list) or len(config["dialogue"]) == 0:
        raise ValueError("dialogue must be a non-empty list")
    
    for i, line in enumerate(config["dialogue"]):
        if "caption" not in line or "speaker" not in line:
            raise ValueError(f"Dialogue line {i} missing required fields (caption, speaker)")
        if line["speaker"] not in ["PETER", "STEWIE"]:
            raise ValueError(f"Dialogue line {i} has invalid speaker: {line['speaker']}")
    
    # Check image paths if images are referenced
    image_paths = config.get("images", {})
    for filename, path in image_paths.items():
        if not Path(path).exists():
            raise FileNotFoundError(f"Image file not found: {path} (referenced as {filename})")
    
    print("✅ Config validation passed")


def main():
    parser = argparse.ArgumentParser(
        description="Test image overlay in videos without running full pipeline"
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to JSON config file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Override output file path from config"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed FFmpeg output"
    )
    parser.add_argument(
        "--karaoke",
        action="store_true",
        help="Use karaoke-style captions (word-by-word yellow highlight) instead of box captions"
    )
    
    args = parser.parse_args()
    
    # Load config
    if not args.config.exists():
        print(f"❌ Config file not found: {args.config}")
        sys.exit(1)
    
    try:
        with open(args.config, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config file: {e}")
        sys.exit(1)
    
    # Validate config
    try:
        validate_config(config)
    except (ValueError, FileNotFoundError) as e:
        print(f"❌ Config validation failed: {e}")
        sys.exit(1)
    
    # Determine output file
    output_file = args.output if args.output else Path(config.get("output_file", "tmp/test_videos/test_output.mp4"))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Get audio duration
    audio_file = Path(config["audio_file"])
    print(f"\n🎵 Analyzing audio file: {audio_file}")
    audio_duration = get_audio_duration(audio_file)
    print(f"   Duration: {audio_duration:.2f} seconds")
    
    # Calculate caption timings
    print(f"\n⏱️  Calculating caption timings for {len(config['dialogue'])} lines...")
    caption_timings = calculate_caption_timings(config["dialogue"], audio_duration)
    
    if args.verbose:
        print("\nCaption timing breakdown:")
        for i, timing in enumerate(caption_timings):
            print(f"  {i+1}. [{timing['start']:.2f}s - {timing['end']:.2f}s] {timing['speaker']}: {timing['caption']}")
    
    # Build educational images list
    educational_images = []
    if "images" in config:
        print(f"\n🖼️  Processing educational images...")
        educational_images = build_educational_images_list(
            config["dialogue"],
            caption_timings,
            config["images"]
        )
    
    # Create video
    caption_mode = "karaoke" if args.karaoke else "box"
    print(f"\n🎬 Creating video with image overlays...")
    print(f"   Background: {config['background_video']}")
    print(f"   Output: {output_file}")
    print(f"   Caption mode: {caption_mode}")
    
    try:
        result_path = create_video_with_audio_and_captions(
            background_video=config["background_video"],
            audio_file=str(audio_file),
            caption_timings=caption_timings,
            output_file=str(output_file),
            educational_images=educational_images,
            caption_mode=caption_mode,
        )
        
        print(f"\n✅ Video created successfully!")
        print(f"   Output: {result_path}")
        print(f"\nYou can now review the video to verify image overlay positioning and timing.")
        
    except Exception as e:
        print(f"\n❌ Video creation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
