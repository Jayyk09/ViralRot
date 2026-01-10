#!/usr/bin/env python3
"""
Test script for quiz transcript extraction and video generation pipeline.

This script demonstrates how to:
1. Extract quiz transcripts from various input types (audio, text, YouTube)
2. Generate a quiz video from the extracted transcripts

Usage:
    # Test with audio file
    python test_quiz_pipeline.py --input assets/sample_audio.mp3 --type audio
    
    # Test with text file
    python test_quiz_pipeline.py --input assets/sample_lecture.txt --type text
    
    # Test with YouTube URL
    python test_quiz_pipeline.py --input "https://www.youtube.com/watch?v=..." --type youtube
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from frontend_pipeline.script_generation.transcripts import extract_quiz_transcripts
from backend_pipeline.generate_quiz_video import generate_quiz_video


def test_quiz_extraction(input_path: str, file_type: str, output_json: Path):
    """
    Test quiz transcript extraction.
    
    Args:
        input_path: Path to input file or YouTube URL
        file_type: Type of input ('audio', 'text', 'youtube', 'pptx')
        output_json: Path to save extracted quiz JSON
    """
    print("=" * 60)
    print("STEP 1: Extract Quiz Transcripts")
    print("=" * 60)
    print(f"Input: {input_path}")
    print(f"Type: {file_type}")
    print()
    
    try:
        # Extract quiz transcripts
        quiz_modules = extract_quiz_transcripts(input_path, file_type)
        
        print(f"\n✅ Successfully extracted {len(quiz_modules)} quiz modules!")
        
        # Display summary
        for idx, module in enumerate(quiz_modules, 1):
            print(f"\n📚 Module {idx}: {module.subtopic_title}")
            print(f"   Questions: {len(module.questions)}")
            for q_idx, question in enumerate(module.questions, 1):
                print(f"   {q_idx}. {question.type}: {question.question_text[:50]}...")
        
        # Save to JSON
        output_json.parent.mkdir(parents=True, exist_ok=True)
        
        quiz_data = {
            "quiz_modules": [module.model_dump() for module in quiz_modules]
        }
        
        with output_json.open("w") as f:
            json.dump(quiz_data, f, indent=2)
        
        print(f"\n💾 Quiz transcripts saved to: {output_json}")
        return quiz_modules
        
    except Exception as e:
        print(f"\n❌ Error extracting quiz transcripts: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_quiz_video_generation(quiz_json: Path, background_video: Path, user_id: int = 1):
    """
    Test quiz video generation.
    
    Args:
        quiz_json: Path to quiz JSON file
        background_video: Path to background video or directory
        user_id: User ID for database entry
    """
    print("\n" + "=" * 60)
    print("STEP 2: Generate Quiz Video")
    print("=" * 60)
    print(f"Quiz data: {quiz_json}")
    print(f"Background: {background_video}")
    print()
    
    try:
        from backend_pipeline.generate_quiz_video import generate_quiz_video_from_file
        
        result = generate_quiz_video_from_file(
            quiz_path=quiz_json,
            background_video=background_video,
            output_dir=Path("assets/output/quiz"),
            audio_dir=Path("assets/audio/quiz"),
            user_id=user_id,
        )
        
        print("\n" + "=" * 60)
        print("✅ QUIZ VIDEO GENERATION COMPLETE!")
        print("=" * 60)
        print(f"Title: {result['video_title']}")
        print(f"S3 Key: {result['s3_key']}")
        print(f"Description: {result['video_description']}")
        
        if 'presigned_url' in result:
            print(f"\n🔗 Watch video: {result['presigned_url']}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error generating quiz video: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Test quiz transcript extraction and video generation pipeline."
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input file path or YouTube URL",
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=["audio", "text", "youtube", "pptx"],
        required=True,
        help="Type of input file",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("assets/test_output/quiz_transcripts.json"),
        help="Path to save extracted quiz JSON",
    )
    parser.add_argument(
        "--background",
        type=Path,
        default=Path("assets/videos"),
        help="Background video path or directory",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        help="User ID for database entry",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract transcripts, don't generate video",
    )
    parser.add_argument(
        "--video-only",
        action="store_true",
        help="Only generate video from existing JSON (requires --output-json to exist)",
    )
    
    args = parser.parse_args()
    
    # Step 1: Extract quiz transcripts (unless video-only mode)
    if not args.video_only:
        quiz_modules = test_quiz_extraction(
            input_path=args.input,
            file_type=args.type,
            output_json=args.output_json,
        )
        
        if quiz_modules is None:
            print("\n❌ Quiz extraction failed. Exiting.")
            sys.exit(1)
        
        if args.extract_only:
            print("\n✅ Extraction complete. Skipping video generation (--extract-only).")
            sys.exit(0)
    else:
        if not args.output_json.exists():
            print(f"❌ Error: {args.output_json} not found. Cannot run --video-only mode.")
            sys.exit(1)
        print(f"📄 Using existing quiz JSON: {args.output_json}")
    
    # Step 2: Generate quiz video
    if not args.background.exists():
        print(f"❌ Error: Background video/directory not found: {args.background}")
        sys.exit(1)
    
    result = test_quiz_video_generation(
        quiz_json=args.output_json,
        background_video=args.background,
        user_id=args.user_id,
    )
    
    if result is None:
        print("\n❌ Quiz video generation failed.")
        sys.exit(1)
    
    print("\n🎉 All tests passed!")


if __name__ == "__main__":
    main()
