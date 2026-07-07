"""MiniMax Text-to-Speech API integration for audio generation."""
import os
import json
import requests
import subprocess
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MiniMax API configuration
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
MINIMAX_API_URL = "https://api.minimax.io/v1/t2a_v2"

# Voice mapping for different speakers
VOICE_MAP = {
    "PETER": os.getenv("MINIMAX_PETER_VOICE", "English_Persuasive_Man"),
    "STEWIE": os.getenv("MINIMAX_STEWIE_VOICE", "English_Insightful_Speaker"),
}


def _merge_word_fragments(subtitle_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge MiniMax's sub-word fragments into whole words.

    MiniMax's word-level subtitle_file splits text into syllable/phoneme-sized
    fragments (e.g. "Hey" -> "He" + "y"), not whole words - confirmed against a
    live API response. Concatenating every fragment's text reproduces the
    original string exactly, so whole "visual" words are reconstructed by
    merging consecutive non-whitespace fragments between whitespace fragments.

    Returns timestamps in seconds (source data is milliseconds).
    """
    words = []
    current_text = ""
    current_start_ms = None
    current_end_ms = None

    for segment in subtitle_segments:
        for frag in segment.get("timestamped_words", []):
            text = frag.get("word", "")
            start_ms = frag.get("time_begin", 0.0)
            end_ms = frag.get("time_end", start_ms)

            if text.strip() == "":
                if current_text:
                    words.append({
                        "word": current_text,
                        "start": round(current_start_ms / 1000.0, 3),
                        "end": round(current_end_ms / 1000.0, 3),
                    })
                    current_text = ""
                    current_start_ms = None
                    current_end_ms = None
                continue

            if current_start_ms is None:
                current_start_ms = start_ms
            current_end_ms = end_ms
            current_text += text

    if current_text:
        words.append({
            "word": current_text,
            "start": round(current_start_ms / 1000.0, 3),
            "end": round(current_end_ms / 1000.0, 3),
        })

    return words


def _fetch_word_timestamps(subtitle_url: str) -> List[Dict[str, Any]]:
    """
    Fetch and parse MiniMax's subtitle_file into merged word-level timestamps.

    Returns an empty list (never raises) on any failure so missing/unreliable
    captions never fail the whole audio generation job - callers should fall
    back to line-level timing when this comes back empty.
    """
    try:
        response = requests.get(subtitle_url, timeout=15)
        response.raise_for_status()
        segments = response.json()
        if not isinstance(segments, list):
            print(f"⚠️  Unexpected subtitle_file shape (expected list): {type(segments)}")
            return []
        return _merge_word_fragments(segments)
    except Exception as e:
        print(f"⚠️  Failed to fetch/parse subtitle_file: {e}")
        return []


def generate_audio_from_dialouge(dialouge: str, voice_id: str) -> tuple[bytes, float, List[Dict[str, Any]]]:
    """
    Call MiniMax TTS API for a single text segment.

    Args:
        text: Text to synthesize
        voice_id: MiniMax voice ID

    Returns:
        Tuple of (audio_bytes, duration_seconds, word_timestamps)
        word_timestamps is a list of {word, start, end} in seconds, relative
        to the start of this segment's own audio (0-based). Empty if MiniMax's
        subtitle_file was unavailable or unparseable.

    Raises:
        Exception: If API call fails
    """
    if not MINIMAX_API_KEY:
        raise ValueError("MINIMAX_API_KEY not found in environment variables")
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Add GroupId as query parameter
    params = {
        "GroupId": MINIMAX_GROUP_ID,
    }
    
    payload = {
        "model": "speech-2.6-hd",
        "text": dialouge,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.3,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "output_format": "hex",
        "subtitle_enable": True,
        "subtitle_type": "word",
    }

    response = requests.post(MINIMAX_API_URL, headers=headers, params=params, json=payload, timeout=30)
    
    # Check for errors
    if response.status_code != 200:
        raise Exception(
            f"MiniMax API error (status {response.status_code}): {response.text}"
        )
    
    result = response.json()
    
    # Check base response status
    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code") != 0:
        status_msg = base_resp.get("status_msg", "Unknown error")
        raise Exception(f"MiniMax API error: {status_msg}")


    '''
    MiniMax response type (confirmed live with subtitle_enable=True, subtitle_type="word"):
        {
          "data": {
            "audio": "<hex encoded audio>",
            "status": 2,
            "subtitle_file": "https://...signed-download-url..."
          },
          "extra_info": {
            "audio_length": 11124,
            "audio_sample_rate": 32000,
            "audio_size": 179926,
            "bitrate": 128000,
            "word_count": 163,
            "invisible_character_ratio": 0,
            "usage_characters": 163,
            "audio_format": "mp3",
            "audio_channel": 1
          },
          "trace_id": "01b8bf9bb7433cc75c18eee6cfa8fe21",
          "base_resp": {
            "status_code": 0,
            "status_msg": "success"
          }
        }

    subtitle_file is a download link, NOT inline timestamps - it must be
    fetched separately. Its contents are a JSON list of segments, each with
    timestamped_words: sub-word fragments in milliseconds (see
    _merge_word_fragments for why these need merging into whole words).
    '''

    # Extract audio data
    data = result.get("data", {})
    if not data["audio"]:
        raise Exception("No audio data in MiniMax response")

    hex_audio = data["audio"]
    audio_bytes = bytes.fromhex(hex_audio)

    # Get duration from extra_info
    extra_info = result.get("extra_info", {})
    duration_ms = extra_info.get("audio_length", 0)
    duration_sec = round(duration_ms / 1000.0, 3)

    word_timestamps = []
    subtitle_url = data.get("subtitle_file")
    if subtitle_url:
        word_timestamps = _fetch_word_timestamps(subtitle_url)

    return audio_bytes, duration_sec, word_timestamps



def generate_audio_from_transcript(
    transcript_data: Dict[str, Any], output_dir: str = "assets/audio/segments"
) -> List[Dict[str, Any]]:
    """
    Generate audio files from transcript JSON data using MiniMax TTS.

    Args:
        transcript_data: Dictionary containing 'transcripts' list with caption and speaker
        output_dir: Directory to save audio segments

    Returns:
        List of audio segment dictionaries with file paths and metadata
    """
    print(f"\n{'='*60}")
    print(f"🔍 GENERATE_AUDIO_FROM_TRANSCRIPT - ENTRY")
    print(f"{'='*60}")
    print(f"  transcript_data type: {type(transcript_data)}")
    print(f"  transcript_data keys: {transcript_data.keys() if transcript_data else 'None'}")

    transcripts = transcript_data.get("transcripts")
    print(f"  transcripts type: {type(transcripts)}")
    print(f"  transcripts is None: {transcripts is None}")
    print(f"  transcripts length: {len(transcripts) if transcripts else 'N/A'}")

    if not transcripts:
        raise ValueError("No transcripts found in transcript_data")

    # Log first few transcripts
    for i, seg in enumerate(transcripts[:3]):
        print(f"  transcripts[{i}]: caption={seg.get('caption', 'MISSING')[:30] if seg.get('caption') else 'None'}...")
    print(f"{'='*60}\n")

    os.makedirs(output_dir, exist_ok=True)

    audio_segments = []

    for idx, segment in enumerate(transcripts):
        caption = segment["caption"]
        speaker = segment["speaker"]
        emotion = segment.get("emotion", "neutral")  # Default to neutral if not provided
        
        # Get voice ID for speaker
        voice_id = VOICE_MAP.get(speaker, VOICE_MAP["PETER"])
        
        print(
            f"🎙️  Generating audio {idx+1}/{len(transcripts)}: "
            f"{speaker} ({emotion})"
        )
        
        try:
            # Generate audio via MiniMax API
            audio_bytes, duration, word_timestamps = generate_audio_from_dialouge(caption, voice_id)

            # Save audio to file
            output_file = os.path.join(
                output_dir, f"segment_{idx:03d}_{speaker.lower()}.mp3"
            )
            with open(output_file, "wb") as f:
                f.write(audio_bytes)

            audio_segments.append(
                {
                    "index": idx,
                    "file": output_file,
                    "caption": caption,
                    "speaker": speaker,
                    "emotion": emotion,
                    "duration": duration,
                    "word_timestamps": word_timestamps,  # 0-based, relative to this segment
                }
            )
            
            print(f"   ✅ Saved: {output_file} ({duration:.2f}s)")
            
        except Exception as e:
            print(f"   ❌ Failed to generate audio for segment {idx}: {e}")
            raise
    
    return audio_segments


def concatenate_audio_segments(
    audio_segments: List[Dict[str, Any]], output_file: str = "assets/audio/full_audio.mp3"
) -> Dict[str, Any]:
    """
    Concatenate all audio segments into a single file with metadata.
    
    Args:
        audio_segments: List of audio segment dictionaries
        output_file: Output file path for concatenated audio
    
    Returns:
        Dictionary with audio file path and segment timings
    """
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
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        abs_list_file,
        "-c",
        "copy",
        abs_output_file,
    ]
    
    print(f"🔗 Concatenating {len(audio_segments)} audio segments...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ FFmpeg concatenation failed!")
        print(f"   Command: {' '.join(cmd)}")
        print(f"   stderr: {result.stderr}")
        raise Exception(f"FFmpeg concatenation failed: {result.stderr}")
    
    # Calculate timings based on durations from MiniMax API
    timings = []
    word_timestamps = []
    current_time = 0.0

    for segment in audio_segments:
        duration = segment.get("duration", 0.0)

        if duration == 0.0:
            # Probe the actual audio file to get the real duration
            print(f"⚠️  Warning: No duration info for segment {segment['index']}, probing audio file...")
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                segment["file"],
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            if probe_result.returncode == 0 and probe_result.stdout.strip():
                duration = round(float(probe_result.stdout.strip()), 3)
                print(f"   ✅ Probed duration: {duration:.3f}s")
            else:
                print(f"   ❌ Could not probe duration, using fallback of 1.0s")
                duration = 1.0

        timings.append(
            {
                "index": segment["index"],
                "start": round(current_time, 3),
                "end": round(current_time + duration, 3),
                "duration": round(duration, 3),
                "caption": segment["caption"],
                "speaker": segment["speaker"],
                "emotion": segment.get("emotion", "neutral"),
            }
        )

        # Offset this segment's local (0-based) word timestamps onto the full timeline
        for word in segment.get("word_timestamps", []) or []:
            word_timestamps.append(
                {
                    "word": word["word"],
                    "start": round(current_time + word["start"], 3),
                    "end": round(current_time + word["end"], 3),
                    "line_index": segment["index"],
                }
            )

        current_time += duration

    print(f"✅ Full audio saved: {output_file} (Total duration: {current_time:.2f}s)")

    return {
        "audio_file": output_file,
        "total_duration": current_time,
        "timings": timings,
        "word_timestamps": word_timestamps,
    }


if __name__ == "__main__":
    # Test script
    print("Testing MiniMax TTS integration...")
    
    # Sample transcript
    test_transcript = {
        "transcripts": [
            {"caption": "Hey Stewie, did you know about photosynthesis?", "speaker": "PETER"},
            {"caption": "Of course I do, Peter. It's elementary biology.", "speaker": "STEWIE"},
            {"caption": "Plants use sunlight to make food!", "speaker": "PETER"},
        ]
    }
    
    # Test directory
    test_output_dir = "test_audio_minimax"
    
    try:
        # Generate audio segments
        segments = generate_audio_from_transcript(test_transcript, test_output_dir)
        
        # Concatenate segments
        result = concatenate_audio_segments(segments, f"{test_output_dir}/full.mp3")
        
        print(f"\n🎉 Test complete! Total duration: {result['total_duration']:.2f} seconds")
        print(f"📄 Generated {len(result['timings'])} audio segments")
        print(f"\nTest files saved to: {test_output_dir}/")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
