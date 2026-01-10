#!/usr/bin/env python3
"""
Quick test using FastAPI endpoints for quiz generation.

This script demonstrates testing the quiz pipeline through the API endpoints.
"""

import requests
import json
import time
from pathlib import Path


def test_quiz_extraction_api(file_path: str, file_type: str, base_url: str = "http://localhost:8000"):
    """
    Test quiz extraction via API endpoint.
    
    Args:
        file_path: Path to file or YouTube URL
        file_type: Type of input ('audio', 'text', 'youtube')
        base_url: Base URL of FastAPI server
    """
    print("=" * 60)
    print("Testing Quiz Extraction API")
    print("=" * 60)
    
    url = f"{base_url}/extract-quiz-transcripts"
    
    if file_type == "youtube":
        # For YouTube, send as form data with URL
        data = {"file_type": file_type}
        files = {"file": (None, file_path)}
    else:
        # For files, upload the actual file
        with open(file_path, "rb") as f:
            files = {"file": (Path(file_path).name, f, "application/octet-stream")}
            data = {"file_type": file_type}
            
            response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        quiz_data = response.json()
        print(f"✅ Successfully extracted {len(quiz_data['quiz_modules'])} quiz modules")
        
        # Display summary
        for idx, module in enumerate(quiz_data["quiz_modules"], 1):
            print(f"\n📚 Module {idx}: {module['subtopic_title']}")
            print(f"   Questions: {len(module['questions'])}")
        
        return quiz_data
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None


def test_quiz_video_generation_api(quiz_modules: list, user_id: int = 1, base_url: str = "http://localhost:8000"):
    """
    Test quiz video generation via API endpoint.
    
    Args:
        quiz_modules: List of quiz module dictionaries
        user_id: User ID
        base_url: Base URL of FastAPI server
    """
    print("\n" + "=" * 60)
    print("Testing Quiz Video Generation API")
    print("=" * 60)
    
    url = f"{base_url}/generate-quiz-videos"
    
    payload = {
        "user_id": user_id,
        "quiz_modules": quiz_modules
    }
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Quiz video generated successfully!")
        print(f"Title: {result.get('video_title', 'N/A')}")
        print(f"S3 Key: {result.get('s3_key', 'N/A')}")
        
        if 'presigned_url' in result:
            print(f"\n🔗 Watch video: {result['presigned_url']}")
        
        return result
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test quiz pipeline via API")
    parser.add_argument("--input", type=str, required=True, help="Input file or YouTube URL")
    parser.add_argument("--type", type=str, required=True, choices=["audio", "text", "youtube"])
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--base-url", type=str, default="http://localhost:8000")
    parser.add_argument("--extract-only", action="store_true", help="Only test extraction")
    
    args = parser.parse_args()
    
    # Test extraction
    quiz_data = test_quiz_extraction_api(
        file_path=args.input,
        file_type=args.type,
        base_url=args.base_url
    )
    
    if quiz_data is None:
        print("❌ Extraction failed")
        return
    
    if args.extract_only:
        print("\n✅ Extraction test complete")
        return
    
    # Test video generation
    result = test_quiz_video_generation_api(
        quiz_modules=quiz_data["quiz_modules"],
        user_id=args.user_id,
        base_url=args.base_url
    )
    
    if result:
        print("\n🎉 All API tests passed!")
    else:
        print("\n❌ Video generation failed")


if __name__ == "__main__":
    main()
