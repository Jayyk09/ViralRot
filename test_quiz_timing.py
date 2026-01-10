import sys
import os
sys.path.insert(0, '.')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from backend_pipeline.generate_quiz_video import generate_quiz_video_from_file
from pathlib import Path

print("Testing quiz video with options display...")

result = generate_quiz_video_from_file(
    quiz_path=Path("assets/test_output/quiz_transcripts.json"),
    background_video=Path("assets/videos"),
    output_dir=Path("assets/output/quiz_test2"),
    audio_dir=Path("assets/audio/quiz_test2"),
    user_id=1,
)

print("\nSuccess!")
print(f"Video ID: {result['video_id']}")
print(f"S3 Key: {result['s3_key']}")
print(f"Title: {result['video_title']}")
