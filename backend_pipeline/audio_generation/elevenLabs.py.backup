from elevenlabs.client import ElevenLabs
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

client = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY")
)

# Voice mapping for different speakers
VOICE_MAP = {
    "PETER": os.getenv("Peter_voiceId"),  # Male voice
    "STEWIE": os.getenv("Stewie_voiceId"),  # Child/younger voice
}

def generate_audio_from_transcript(transcript_data, output_dir="assets/audio/segments"):
    """
    Generate audio files from transcript JSON data.
    
    Args:
        transcript_data: Dictionary containing 'transcripts' list with caption and speaker
        output_dir: Directory to save audio segments
    
    Returns:
        List of tuples containing (audio_file_path, caption, speaker, duration)
    """
    os.makedirs(output_dir, exist_ok=True)
    
    audio_segments = []
    
    for idx, segment in enumerate(transcript_data["transcripts"]):
        caption = segment["caption"]
        speaker = segment["speaker"]
        emotion = segment.get("emotion", "neutral")  # Default to neutral if not provided
        
        # Get voice ID for speaker
        voice_id = VOICE_MAP.get(speaker, VOICE_MAP["PETER"])
        
        print(f"🎙️  Generating audio {idx+1}/{len(transcript_data['transcripts'])}: {speaker} ({emotion})")
        
        # Generate audio
        audio = client.text_to_speech.convert(
            text=caption,
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        # Save audio to file
        output_file = os.path.join(output_dir, f"segment_{idx:03d}_{speaker.lower()}.mp3")
        with open(output_file, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        
        audio_segments.append({
            "index": idx,
            "file": output_file,
            "caption": caption,
            "speaker": speaker,
            "emotion": emotion
        })
        
        print(f"   ✅ Saved: {output_file}")
    
    return audio_segments

def concatenate_audio_segments(audio_segments, output_file="assets/audio/full_audio.mp3"):
    """
    Concatenate all audio segments into a single file with metadata.
    
    Args:
        audio_segments: List of audio segment dictionaries
        output_file: Output file path for concatenated audio
    
    Returns:
        Dictionary with audio file path and segment timings
    """
    import subprocess
    
    # Create a file list for ffmpeg
    segments_dir = os.path.dirname(audio_segments[0]["file"])
    list_file = os.path.join(segments_dir, "filelist.txt")
    
    with open(list_file, "w") as f:
        for segment in audio_segments:
            f.write(f"file '{os.path.basename(segment['file'])}'\n")
    
    # Make sure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
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
    
    print(f"🔗 Concatenating {len(audio_segments)} audio segments...")
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
        if not os.path.exists(segment["file"]):
            print(f"⚠️  Warning: Segment file not found: {segment['file']}")
            continue
            
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
            
        duration = float(result.stdout.strip())
        
        timings.append({
            "index": segment["index"],
            "start": current_time,
            "end": current_time + duration,
            "duration": duration,
            "caption": segment["caption"],
            "speaker": segment["speaker"],
            "emotion": segment.get("emotion", "neutral")
        })
        
        current_time += duration
    
    print(f"✅ Full audio saved: {output_file} (Total duration: {current_time:.2f}s)")
    
    return {
        "audio_file": output_file,
        "total_duration": current_time,
        "timings": timings
    }

if __name__ == "__main__":
    # Load sample transcript
    with open("assets/sample.json", "r") as f:
        transcript_data = json.load(f)
    
    # Generate audio segments
    audio_segments = generate_audio_from_transcript(transcript_data)
    
    # Concatenate segments
    result = concatenate_audio_segments(audio_segments)
    
    print(f"\n🎉 Complete! Total duration: {result['total_duration']:.2f} seconds")
    print(f"📄 Generated {len(result['timings'])} audio segments")
