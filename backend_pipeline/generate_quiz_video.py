#!/usr/bin/env python3
"""
Generate a single quiz video from quiz transcript modules.

This pipeline takes quiz modules (questions with Peter's ask/reveal scripts),
generates audio for each script line, concatenates them, and creates a final
video with captions and character images.

Usage:
    python backend_pipeline/generate_quiz_video.py \
        --quiz-transcripts assets/quiz_output.json \
        --background assets/videos/minecraft.mp4 \
        --output-dir assets/output/quiz
"""

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List

from save_to_db.save_video import add_video

from backend_pipeline.audio_generation.elevenLabs_quiz import (
    generate_audio_from_quiz_transcript,
    concatenate_quiz_audio_segments,
)
from backend_pipeline.video_assembly.ffMpeg_quiz import (
    create_quiz_video_with_audio_and_captions,
)
from save_to_db.collection_service import find_last_collection


def get_random_background_video(videos_dir: Path | str) -> Path:
    """
    Randomly select a background video from the videos directory.
    Returns the path to the selected video.
    """
    videos_path = Path(videos_dir)
    
    if not videos_path.exists():
        raise FileNotFoundError(f"Background videos directory not found at {videos_dir}")
    
    video_files = list(videos_path.glob("*.mp4"))
    
    if not video_files:
        raise FileNotFoundError(f"No background videos found in {videos_dir}")
    
    selected_video = random.choice(video_files)
    
    return selected_video


def load_quiz_modules(path: Path) -> List[Dict[str, Any]]:
    """Load quiz modules from JSON file."""
    with path.open("r") as f:
        data = json.load(f)

    if "quiz_modules" in data:
        return data["quiz_modules"]
    raise ValueError("JSON must contain 'quiz_modules'.")


def convert_quiz_to_transcript_format(quiz_modules: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """
    Convert quiz modules to transcript format for audio generation.
    
    Creates a linear sequence of Peter's ask/reveal scripts for all questions
    across all quiz modules.
    
    Returns:
        Dictionary with 'transcripts' list containing caption, speaker, emotion for each line
    """
    transcripts = []
    
    for module in quiz_modules:
        subtopic_title = module["subtopic_title"]
        
        # Add intro line for the subtopic
        transcripts.append({
            "caption": f"Alright, time to test your knowledge on {subtopic_title}!",
            "speaker": "PETER",
            "emotion": "excited"
        })
        
        for question in module["questions"]:
            question_num = question["question_number"]
            question_type = question["type"]
            script = question["script"]
            
            # Add the "ask" script
            transcripts.append({
                "caption": script["ask"],
                "speaker": "PETER",
                "emotion": "teaching"
            })
            
            # For multiple choice questions, display options during pause
            if question_type == "multiple_choice" and question.get("options"):
                # Format options as A) B) C) D)
                options_text = "\n".join([
                    f"{chr(65 + i)}) {opt}" 
                    for i, opt in enumerate(question["options"])
                ])
                transcripts.append({
                    "caption": options_text,
                    "speaker": "PETER",
                    "emotion": "teaching",
                    "is_options": True  # Flag to identify this as options display
                })
            else:
                # For other question types, use pause indicator
                transcripts.append({
                    "caption": "[Pause to think...]",
                    "speaker": "PETER",
                    "emotion": "teaching"
                })
            
            # Add the "reveal" script
            transcripts.append({
                "caption": script["reveal"],
                "speaker": "PETER",
                "emotion": "excited"
            })
    
    # Add closing line
    transcripts.append({
        "caption": "Great job! You're getting smarter every day!",
        "speaker": "PETER",
        "emotion": "excited"
    })
    
    return {"transcripts": transcripts}


def generate_quiz_video(
    quiz_modules: List[Dict[str, Any]],
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
) -> Dict[str, str]:
    """
    Generate a single quiz video from quiz modules.
    
    Args:
        quiz_modules: List of quiz module dictionaries
        background_video: Path to background video or directory of videos
        output_dir: Directory to store generated video
        audio_dir: Directory to store generated audio assets
        user_id: User ID for database entry
    
    Returns:
        Dictionary with video info (s3_key, title, etc.)
    """
    background_video_path = Path(background_video)
    output_dir = Path(output_dir)
    audio_dir = Path(audio_dir)

    if not quiz_modules:
        raise ValueError("No quiz modules provided.")

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Select background video
    if background_video_path.is_dir():
        selected_background = get_random_background_video(background_video_path)
    else:
        selected_background = background_video_path

    print(f"\n🎬 Generating quiz video...")
    print(f"   Background: {selected_background.name}")
    print(f"   Quiz modules: {len(quiz_modules)}")

    # Convert quiz modules to transcript format
    transcript_data = convert_quiz_to_transcript_format(quiz_modules)
    
    # Generate audio segments
    print(f"\n🎤 Generating quiz audio for {len(transcript_data['transcripts'])} segments...")
    audio_segments = generate_audio_from_quiz_transcript(
        transcript_data,
        output_dir=str(audio_dir)
    )

    # Concatenate audio (with 2-second pauses and 5-second options display)
    print(f"\n🔗 Concatenating quiz audio segments...")
    full_audio_path = audio_dir / "quiz_full_audio.mp3"
    audio_result = concatenate_quiz_audio_segments(
        audio_segments,
        output_file=str(full_audio_path),
        pause_duration=2.0,
        options_duration=5.0
    )

    # Prepare caption timings for video
    caption_timings = audio_result["segments"]

    # Generate final quiz video
    print(f"\n🎥 Creating final quiz video...")
    video_output_path = output_dir / "quiz_video.mp4"
    
    create_quiz_video_with_audio_and_captions(
        background_video=str(selected_background),
        audio_file=str(full_audio_path),
        caption_timings=caption_timings,
        output_file=str(video_output_path),
        video_size=(1080, 1920),  # Portrait for TikTok/Reels
    )

    print(f"\n✅ Quiz video created: {video_output_path}")

    # Upload to S3 and save to database
    print(f"\n☁️  Uploading quiz video to S3 and database...")
    
    # Generate title from quiz modules
    subtopic_titles = [module["subtopic_title"] for module in quiz_modules]
    quiz_title = f"Quiz: {', '.join(subtopic_titles[:2])}"  # First 2 topics
    if len(subtopic_titles) > 2:
        quiz_title += f" +{len(subtopic_titles) - 2} more"
    
    description = f"Test your knowledge with {sum(len(m['questions']) for m in quiz_modules)} questions"
    
    # Get the last collection ID (returns dict with 'id' or None)
    collection_dict = find_last_collection(user_id)
    collection_id = collection_dict["id"] if collection_dict else None

    # Open video file and upload
    with open(video_output_path, "rb") as video_file:
        video_id = add_video(
            user_id=user_id,
            file_obj=video_file,
            original_filename=video_output_path.name,
            title=quiz_title,
            description=description,
            collection_id=collection_id,  # Link to the last collection
        )
    
    # Generate S3 key (matches the pattern used in upload_video_to_s3)
    file_extension = video_output_path.suffix
    s3_key = f"{user_id}/{video_id}{file_extension}"

    print(f"\n🎉 Quiz video uploaded successfully!")
    print(f"   Title: {quiz_title}")
    print(f"   Video ID: {video_id}")
    print(f"   S3 Key: {s3_key}")

    return {
        "video_id": video_id,
        "s3_key": s3_key,
        "video_title": quiz_title,
        "video_description": description,
        "video_path": str(video_output_path),
    }


def generate_quiz_video_from_file(
    quiz_path: Path,
    background_video: Path,
    output_dir: Path,
    audio_dir: Path,
    user_id: int,
) -> Dict[str, str]:
    """Load quiz from file and generate video."""
    quiz_modules = load_quiz_modules(quiz_path)
    return generate_quiz_video(
        quiz_modules=quiz_modules,
        background_video=background_video,
        output_dir=output_dir,
        audio_dir=audio_dir,
        user_id=user_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate quiz video from quiz transcripts.")
    parser.add_argument(
        "--quiz-transcripts",
        type=Path,
        required=True,
        help="Path to JSON file with quiz_modules output.",
    )
    parser.add_argument(
        "--background",
        type=Path,
        required=True,
        help="Background video path or directory (e.g., assets/videos/).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/output/quiz"),
        help="Directory to store generated video.",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path("assets/audio/quiz"),
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

    if not args.quiz_transcripts.exists():
        raise FileNotFoundError(f"Quiz transcripts not found: {args.quiz_transcripts}")
    if not args.background.exists():
        raise FileNotFoundError(f"Background video not found: {args.background}")

    result = generate_quiz_video_from_file(
        quiz_path=args.quiz_transcripts,
        background_video=args.background,
        output_dir=args.output_dir,
        audio_dir=args.audio_dir,
        user_id=args.user_id,
    )

    print("\n=== Summary ===")
    print(f"Video Title: {result['video_title']}")
    print(f"S3 Key: {result['s3_key']}")
    print(f"Description: {result['video_description']}")


if __name__ == "__main__":
    main()
