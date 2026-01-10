#!/usr/bin/env python3
"""
Generate a complete collection: subtopic videos + quiz video from a single source.

This pipeline:
1. Takes a single source (youtube/audio/pptx/text)
2. Extracts subtopic transcripts and generates N subtopic videos
3. Extracts quiz from the same source and generates 1 quiz video
4. Stores all videos in the same collection with the quiz as the final entry

Usage:
    python backend_pipeline/generate_complete_collection.py \
        --source test.txt \
        --source-type text \
        --background assets/videos \
        --user-id 1
"""

import argparse
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from frontend_pipeline.script_generation.transcripts import (
    extract_transcripts,
    extract_quiz_transcripts,
)
from backend_pipeline.generate_subtopic_videos import generate_videos_from_subtopic_list
from backend_pipeline.generate_quiz_video import generate_quiz_video
from save_to_db.collection_service import create_collection, generate_collection_title


def generate_complete_collection(
    source: str,
    source_type: str,
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
) -> Dict[str, Any]:
    """
    Generate a complete collection of subtopic videos + quiz video from a single source.
    
    Args:
        source: Path to file or content string (youtube URL, text, etc.)
        source_type: Type of source ('audio', 'audio/mp3', 'text', 'youtube', 'pptx')
        background_video: Path to background video file or directory of videos
        output_dir: Root directory to store generated videos
        audio_dir: Root directory to store generated audio assets
        user_id: User ID for database entry
    
    Returns:
        Dictionary with collection info and all video results
    """
    background_video_path = Path(background_video)
    output_dir = Path(output_dir)
    audio_dir = Path(audio_dir)
    
    # Create unique session ID for this collection
    session_id = uuid4().hex
    
    # Create subdirectories for this session
    subtopic_video_dir = output_dir / f"collection_{session_id}" / "subtopics"
    subtopic_audio_dir = audio_dir / f"collection_{session_id}" / "subtopics"
    quiz_video_dir = output_dir / f"collection_{session_id}" / "quiz"
    quiz_audio_dir = audio_dir / f"collection_{session_id}" / "quiz"
    
    subtopic_video_dir.mkdir(parents=True, exist_ok=True)
    subtopic_audio_dir.mkdir(parents=True, exist_ok=True)
    quiz_video_dir.mkdir(parents=True, exist_ok=True)
    quiz_audio_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("🚀 Starting Complete Collection Generation")
    print("="*60)
    print(f"   Source: {source}")
    print(f"   Type: {source_type}")
    print(f"   User ID: {user_id}")
    print(f"   Session ID: {session_id}")
    
    # Step 1: Extract subtopic transcripts
    print("\n" + "="*60)
    print("📝 Step 1: Extracting Subtopic Transcripts")
    print("="*60)
    subtopics = extract_transcripts(source, source_type)
    
    if not subtopics:
        raise ValueError("No subtopics extracted from source.")
    
    print(f"✅ Extracted {len(subtopics)} subtopics")
    for i, subtopic in enumerate(subtopics, start=1):
        print(f"   {i}. {subtopic.subtopic_title}")
    
    # Step 2: Extract quiz transcripts
    print("\n" + "="*60)
    print("❓ Step 2: Extracting Quiz Transcripts")
    print("="*60)
    quiz_modules = extract_quiz_transcripts(source, source_type)
    
    if not quiz_modules:
        raise ValueError("No quiz modules extracted from source.")
    
    total_questions = sum(len(module.questions) for module in quiz_modules)
    print(f"✅ Extracted {len(quiz_modules)} quiz modules with {total_questions} questions")
    for i, module in enumerate(quiz_modules, start=1):
        print(f"   {i}. {module.subtopic_title}: {len(module.questions)} questions")
    
    # Step 3: Create collection
    print("\n" + "="*60)
    print("📁 Step 3: Creating Collection")
    print("="*60)
    subtopic_titles = [subtopic.subtopic_title for subtopic in subtopics]
    collection_title = generate_collection_title(subtopic_titles)
    collection_id = create_collection(user_id, collection_title)
    print(f"✅ Created collection: '{collection_title}' (ID: {collection_id})")
    
    # Step 4: Generate subtopic videos
    print("\n" + "="*60)
    print("🎬 Step 4: Generating Subtopic Videos")
    print("="*60)
    subtopic_dicts = [subtopic.model_dump() for subtopic in subtopics]
    
    # Use a modified version that accepts collection_id
    subtopic_results = generate_videos_from_subtopic_list_with_collection(
        subtopics=subtopic_dicts,
        background_video=background_video_path,
        output_dir=subtopic_video_dir,
        audio_dir=subtopic_audio_dir,
        user_id=user_id,
        collection_id=collection_id,
    )
    
    print(f"✅ Generated {len(subtopic_results)} subtopic videos")
    
    # Step 5: Generate quiz video
    print("\n" + "="*60)
    print("❓ Step 5: Generating Quiz Video")
    print("="*60)
    quiz_dicts = [module.model_dump() for module in quiz_modules]
    
    quiz_result = generate_quiz_video_with_collection(
        quiz_modules=quiz_dicts,
        background_video=background_video_path,
        output_dir=quiz_video_dir,
        audio_dir=quiz_audio_dir,
        user_id=user_id,
        collection_id=collection_id,
        subtopic_count=len(subtopics),
    )
    
    print(f"✅ Generated quiz video")
    
    # Step 6: Summary
    print("\n" + "="*60)
    print("🎉 Collection Generation Complete!")
    print("="*60)
    print(f"   Collection: '{collection_title}' (ID: {collection_id})")
    print(f"   Subtopic Videos: {len(subtopic_results)}")
    print(f"   Quiz Video: 1")
    print(f"   Total Videos: {len(subtopic_results) + 1}")
    print("="*60 + "\n")
    
    return {
        "collection_id": collection_id,
        "collection_title": collection_title,
        "subtopic_count": len(subtopic_results),
        "quiz_count": 1,
        "total_videos": len(subtopic_results) + 1,
        "subtopic_results": subtopic_results,
        "quiz_result": quiz_result,
        "session_id": session_id,
    }


def generate_videos_from_subtopic_list_with_collection(
    subtopics: List[Dict[str, Any]],
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
    collection_id: int,
) -> List[Dict[str, str]]:
    """
    Generate videos from subtopic list with a pre-created collection_id.
    
    This is a modified version of generate_videos_from_subtopic_list that
    accepts an existing collection_id instead of creating a new one.
    """
    from backend_pipeline.generate_subtopic_videos import (
        slugify,
        get_random_background_video,
    )
    from backend_pipeline.audio_generation.elevenLabs import (
        generate_audio_from_transcript,
        concatenate_audio_segments,
    )
    from backend_pipeline.video_assembly.ffMpeg import (
        create_video_with_audio_and_captions,
    )
    from save_to_db.save_video import add_video
    
    background_video_path = Path(background_video)
    output_dir = Path(output_dir)
    audio_dir = Path(audio_dir)

    if not subtopics:
        raise ValueError("No subtopics found in transcript file.")

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Determine if background_video is a directory or a single file
    is_directory = background_video_path.is_dir()

    # Generate all videos and store them temporarily
    video_files = []
    results = []
    
    for index, subtopic in enumerate(subtopics, start=1):
        # Select background video for this subtopic
        if is_directory:
            current_bg_video = get_random_background_video(background_video_path)
            print(f"   🎥 Selected background: {current_bg_video.name}")
        else:
            current_bg_video = background_video_path
        
        slug = slugify(subtopic["subtopic_title"])
        print(f"\n   === Subtopic {index}/{len(subtopics)}: {subtopic['subtopic_title']} ===")

        transcripts_payload = {"transcripts": subtopic["dialogue"]}

        segment_dir = audio_dir / slug / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)

        print("   🎙️  Generating audio segments…")
        audio_segments = generate_audio_from_transcript(
            transcripts_payload,
            output_dir=str(segment_dir),
        )

        audio_output = audio_dir / f"{slug}_full.mp3"
        print("   🔗 Concatenating audio segments…")
        audio_result = concatenate_audio_segments(
            audio_segments,
            output_file=str(audio_output),
        )

        video_output = output_dir / f"{slug}.mp4"
        print("   🎥 Creating video…")
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

    # Upload all videos to S3 and save to database with collection_id
    print(f"\n   ☁️  Uploading {len(video_files)} videos to S3 and database...")
    
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
        print(f"   ✅ Uploaded video_id {video_id} for '{video_info['subtopic_title']}'")

    return results


def generate_quiz_video_with_collection(
    quiz_modules: List[Dict[str, Any]],
    background_video: Path | str,
    output_dir: Path | str,
    audio_dir: Path | str,
    user_id: int,
    collection_id: int,
    subtopic_count: int,
) -> Dict[str, str]:
    """
    Generate a quiz video and add it to an existing collection.
    
    Args:
        quiz_modules: List of quiz module dictionaries
        background_video: Path to background video or directory of videos
        output_dir: Directory to store generated video
        audio_dir: Directory to store generated audio assets
        user_id: User ID for database entry
        collection_id: ID of the collection to add this quiz to
        subtopic_count: Number of subtopics in the collection (for description)
    
    Returns:
        Dictionary with video info (video_id, s3_key, title, etc.)
    """
    from backend_pipeline.generate_quiz_video import (
        get_random_background_video,
        convert_quiz_to_transcript_format,
    )
    from backend_pipeline.audio_generation.elevenLabs_quiz import (
        generate_audio_from_quiz_transcript,
        concatenate_quiz_audio_segments,
    )
    from backend_pipeline.video_assembly.ffMpeg_quiz import (
        create_quiz_video_with_audio_and_captions,
    )
    from save_to_db.save_video import add_video
    
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

    print(f"\n   🎬 Generating quiz video...")
    print(f"      Background: {selected_background.name}")
    print(f"      Quiz modules: {len(quiz_modules)}")

    # Convert quiz modules to transcript format
    transcript_data = convert_quiz_to_transcript_format(quiz_modules)
    
    # Generate audio segments
    print(f"\n   🎤 Generating quiz audio for {len(transcript_data['transcripts'])} segments...")
    audio_segments = generate_audio_from_quiz_transcript(
        transcript_data,
        output_dir=str(audio_dir)
    )

    # Concatenate audio (with 2-second pauses and 5-second options display)
    print(f"\n   🔗 Concatenating quiz audio segments...")
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
    print(f"\n   🎥 Creating final quiz video...")
    video_output_path = output_dir / "quiz_video.mp4"
    
    create_quiz_video_with_audio_and_captions(
        background_video=str(selected_background),
        audio_file=str(full_audio_path),
        caption_timings=caption_timings,
        output_file=str(video_output_path),
        video_size=(1080, 1920),  # Portrait for TikTok/Reels
    )

    print(f"\n   ✅ Quiz video created: {video_output_path}")

    # Upload to S3 and save to database with collection_id
    print(f"\n   ☁️  Uploading quiz video to S3 and database...")
    
    # Generate title from quiz modules
    subtopic_titles = [module["subtopic_title"] for module in quiz_modules]
    quiz_title = f"Quiz: {', '.join(subtopic_titles[:2])}"  # First 2 topics
    if len(subtopic_titles) > 2:
        quiz_title += f" +{len(subtopic_titles) - 2} more"
    
    total_questions = sum(len(module["questions"]) for module in quiz_modules)
    # Mark as final entry in collection
    description = f"Quiz (Final) - {total_questions} questions covering all {subtopic_count} subtopics"
    
    # Open video file and upload
    with open(video_output_path, "rb") as video_file:
        video_id = add_video(
            user_id=user_id,
            file_obj=video_file,
            original_filename=video_output_path.name,
            title=quiz_title,
            description=description,
            collection_id=collection_id,  # Add to the same collection!
        )
    
    # Generate S3 key (matches the pattern used in upload_video_to_s3)
    file_extension = video_output_path.suffix
    s3_key = f"{user_id}/{video_id}{file_extension}"

    print(f"\n   🎉 Quiz video uploaded successfully!")
    print(f"      Title: {quiz_title}")
    print(f"      Video ID: {video_id}")
    print(f"      Collection ID: {collection_id}")
    print(f"      S3 Key: {s3_key}")

    return {
        "video_id": video_id,
        "s3_key": s3_key,
        "video_title": quiz_title,
        "video_description": description,
        "video_path": str(video_output_path),
        "collection_id": collection_id,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate complete collection: subtopic videos + quiz video from a single source."
    )
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Path to file or content string (youtube URL, text, etc.)",
    )
    parser.add_argument(
        "--source-type",
        type=str,
        required=True,
        choices=["audio", "audio/mp3", "text", "youtube", "pptx"],
        help="Type of source",
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
        default=Path("assets/output"),
        help="Root directory to store generated videos.",
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=Path("assets/audio/generated"),
        help="Root directory to store generated audio assets.",
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

    if args.source_type in ["audio", "audio/mp3", "pptx"]:
        source_path = Path(args.source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {args.source}")
    
    if not args.background.exists():
        raise FileNotFoundError(f"Background video not found: {args.background}")

    result = generate_complete_collection(
        source=args.source,
        source_type=args.source_type,
        background_video=args.background,
        output_dir=args.output_dir,
        audio_dir=args.audio_dir,
        user_id=args.user_id,
    )

    print("\n" + "="*60)
    print("📊 FINAL SUMMARY")
    print("="*60)
    print(f"Collection: {result['collection_title']} (ID: {result['collection_id']})")
    print(f"Total Videos: {result['total_videos']}")
    print(f"  - Subtopics: {result['subtopic_count']}")
    print(f"  - Quiz: {result['quiz_count']}")
    print(f"Session ID: {result['session_id']}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
