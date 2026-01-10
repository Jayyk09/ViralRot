from elevenlabs.client import ElevenLabs
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

client = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY")
)

# Quiz videos only use Peter's voice
PETER_VOICE_ID = os.getenv("Peter_voiceId")

def generate_audio_from_quiz_transcript(quiz_transcript_data, output_dir="assets/audio/quiz_segments"):
    """
    Generate audio files from quiz transcript data.
    Only uses Peter's voice for all quiz narration.
    
    Args:
        quiz_transcript_data: Dictionary containing 'transcripts' list with caption, speaker, emotion
        output_dir: Directory to save audio segments
    
    Returns:
        List of dictionaries containing audio segment metadata
    """
    os.makedirs(output_dir, exist_ok=True)
    
    audio_segments = []
    
    for idx, segment in enumerate(quiz_transcript_data["transcripts"]):
        caption = segment["caption"]
        speaker = segment.get("speaker", "PETER")  # Always Peter for quizzes
        emotion = segment.get("emotion", "neutral")
        is_options = segment.get("is_options", False)
        
        # Skip pause indicators and options display (don't generate audio for them)
        if caption.startswith("[") and caption.endswith("]"):
            print(f"⏸️  Skipping pause indicator: {caption}")
            # Still add to segments for timing purposes with minimal duration
            audio_segments.append({
                "index": idx,
                "file": None,  # No audio file for pauses
                "caption": caption,
                "speaker": speaker,
                "emotion": emotion,
                "is_pause": True
            })
            continue
        
        # Skip audio generation for multiple choice options (they're displayed visually)
        if is_options:
            print(f"📋 Skipping audio for options display: {len(caption.split(chr(10)))} options")
            audio_segments.append({
                "index": idx,
                "file": None,  # No audio file for options
                "caption": caption,
                "speaker": speaker,
                "emotion": emotion,
                "is_options": True
            })
            continue
        
        print(f"🎙️  Generating quiz audio {idx+1}/{len(quiz_transcript_data['transcripts'])}: {emotion}")
        
        # Generate audio using Peter's voice
        audio = client.text_to_speech.convert(
            text=caption,
            voice_id=PETER_VOICE_ID,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        # Save audio to file
        output_file = os.path.join(output_dir, f"quiz_segment_{idx:03d}.mp3")
        with open(output_file, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        
        audio_segments.append({
            "index": idx,
            "file": output_file,
            "caption": caption,
            "speaker": speaker,
            "emotion": emotion,
            "is_pause": False
        })
        
        print(f"   ✅ Saved: {output_file}")
    
    return audio_segments

def concatenate_quiz_audio_segments(audio_segments, output_file="assets/audio/quiz_full_audio.mp3", pause_duration=2.0, options_duration=5.0):
    """
    Concatenate all quiz audio segments into a single file with metadata.
    Includes configurable pause duration for pause indicators and options display.
    
    Args:
        audio_segments: List of audio segment dictionaries
        output_file: Output file path for concatenated audio
        pause_duration: Duration in seconds for pause indicators (default 2.0s)
        options_duration: Duration in seconds for options display (default 5.0s)
    
    Returns:
        Dictionary with audio file path and segment timings
    """
    import subprocess
    
    # Make sure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Create silent audio files for pauses and options
    segments_dir = os.path.dirname(audio_segments[0]["file"] or output_file)
    pause_silence_file = os.path.join(segments_dir, "silence_pause.mp3")
    options_silence_file = os.path.join(segments_dir, "silence_options.mp3")
    
    # Generate silence audio file for pauses (2 seconds)
    pause_silence_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(pause_duration),
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        pause_silence_file
    ]
    subprocess.run(pause_silence_cmd, capture_output=True, text=True)
    
    # Generate silence audio file for options (5 seconds)
    options_silence_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(options_duration),
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        options_silence_file
    ]
    subprocess.run(options_silence_cmd, capture_output=True, text=True)
    
    # Create a file list for ffmpeg
    list_file = os.path.join(segments_dir, "quiz_filelist.txt")
    
    with open(list_file, "w") as f:
        for segment in audio_segments:
            if segment.get("is_pause", False):
                # Use pause silence file for pauses
                f.write(f"file '{os.path.basename(pause_silence_file)}'\n")
            elif segment.get("is_options", False):
                # Use options silence file for options display
                f.write(f"file '{os.path.basename(options_silence_file)}'\n")
            elif segment["file"]:
                f.write(f"file '{os.path.basename(segment['file'])}'\n")
    
    # Get absolute paths for ffmpeg
    abs_list_file = os.path.abspath(list_file)
    abs_output_file = os.path.abspath(output_file)
    
    # Concatenate using ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", abs_list_file,
        "-c", "copy",
        abs_output_file
    ]
    
    print(f"🔗 Concatenating {len(audio_segments)} quiz audio segments (with {pause_duration}s pauses)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ FFmpeg concatenation failed!")
        print(f"   Command: {' '.join(cmd)}")
        print(f"   stderr: {result.stderr}")
        raise Exception(f"FFmpeg concatenation failed: {result.stderr}")
    
    # Get duration of each segment using ffprobe
    timings = []
    current_time = 0.0
    
    for segment in audio_segments:
        duration = None
        
        if segment.get("is_pause", False):
            # Use configured pause duration (matches the actual silence file)
            duration = pause_duration
        elif segment.get("is_options", False):
            # Use configured options duration (matches the actual silence file)
            duration = options_duration
        elif segment["file"] and os.path.exists(segment["file"]):
            duration_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                segment["file"]
            ]
            result = subprocess.run(duration_cmd, capture_output=True, text=True)
            
            if result.returncode != 0 or not result.stdout.strip():
                print(f"⚠️  Warning: Could not get duration for {segment['file']}")
                print(f"   stderr: {result.stderr}")
                continue
            
            # Parse duration and add small padding to account for concatenation gaps
            raw_duration = float(result.stdout.strip())
            duration = raw_duration + 0.05  # Add 50ms buffer for concatenation
        else:
            print(f"⚠️  Warning: Segment file not found: {segment.get('file', 'None')}")
            continue
        
        if duration is None:
            continue
        
        timings.append({
            "index": segment["index"],
            "start": current_time,
            "end": current_time + duration,
            "duration": duration,
            "caption": segment["caption"],
            "speaker": segment["speaker"],
            "emotion": segment.get("emotion", "neutral"),
            "is_pause": segment.get("is_pause", False),
            "is_options": segment.get("is_options", False)
        })
        
        current_time += duration
    
    # Verify the actual concatenated file duration
    actual_duration_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        abs_output_file
    ]
    actual_result = subprocess.run(actual_duration_cmd, capture_output=True, text=True)
    
    if actual_result.returncode == 0 and actual_result.stdout.strip():
        actual_duration = float(actual_result.stdout.strip())
        duration_diff = abs(actual_duration - current_time)
        
        if duration_diff > 0.5:  # More than 0.5s difference
            print(f"⚠️  Warning: Calculated duration ({current_time:.2f}s) differs from actual ({actual_duration:.2f}s)")
            print(f"   Adjusting timings to match actual duration...")
            
            # Scale all timings proportionally
            scale_factor = actual_duration / current_time
            for timing in timings:
                timing["start"] *= scale_factor
                timing["end"] *= scale_factor
                timing["duration"] *= scale_factor
            
            current_time = actual_duration
    
    print(f"✅ Full quiz audio saved: {output_file} (Total duration: {current_time:.2f}s)")
    
    # Clean up temporary files
    if os.path.exists(pause_silence_file):
        os.remove(pause_silence_file)
    if os.path.exists(options_silence_file):
        os.remove(options_silence_file)
    if os.path.exists(list_file):
        os.remove(list_file)
    
    return {
        "audio_file": output_file,
        "total_duration": current_time,
        "segments": timings  # Changed from 'timings' to 'segments' to match expected API
    }

if __name__ == "__main__":
    # Example usage
    print("ElevenLabs quiz audio generation module ready!")
    print("Use generate_audio_from_quiz_transcript() to generate quiz audio.")
    print("Quiz videos only use Peter's voice for narration.")
    
    # Example quiz transcript format:
    # quiz_data = {
    #     "transcripts": [
    #         {"caption": "Alright, time to test your knowledge!", "speaker": "PETER", "emotion": "excited"},
    #         {"caption": "What is 2 + 2?", "speaker": "PETER", "emotion": "neutral"},
    #         {"caption": "[Pause to think...]", "speaker": "PETER", "emotion": "neutral"},
    #         {"caption": "The answer is 4!", "speaker": "PETER", "emotion": "excited"}
    #     ]
    # }
    # 
    # audio_segments = generate_audio_from_quiz_transcript(quiz_data)
    # result = concatenate_quiz_audio_segments(audio_segments, pause_duration=2.5)
