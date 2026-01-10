#!/usr/bin/env python3
"""
Test the complete collection pipeline (subtopics + quiz) using a text file.
"""
import sys
import os
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from backend_pipeline.generate_complete_collection import generate_complete_collection

def main():
    # Test with photosynthesis text
    source = str(Path("test_photosynthesis.txt"))
    source_type = "text"
    background_video = Path("assets/videos")
    output_dir = Path("assets/output")
    audio_dir = Path("assets/audio/generated")
    user_id = 1
    
    print("=" * 60)
    print("Testing Complete Collection Pipeline")
    print("=" * 60)
    print(f"Source: {source}")
    print(f"Type: {source_type}")
    print("=" * 60 + "\n")
    
    try:
        result = generate_complete_collection(
            source=source,
            source_type=source_type,
            background_video=background_video,
            output_dir=output_dir,
            audio_dir=audio_dir,
            user_id=user_id,
        )
        
        print("\n" + "=" * 60)
        print("✅ TEST PASSED!")
        print("=" * 60)
        print(f"Collection ID: {result['collection_id']}")
        print(f"Collection Title: {result['collection_title']}")
        print(f"Total Videos: {result['total_videos']}")
        print(f"  - Subtopics: {result['subtopic_count']}")
        print(f"  - Quiz: {result['quiz_count']}")
        print("=" * 60)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED!")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
