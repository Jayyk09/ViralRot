import subprocess
import os
import json
import textwrap

def wrap_caption_text(text, max_chars=32):
    """Wrap caption text to a maximum characters per line (word-aware)."""
    wrapped_lines = textwrap.wrap(text, width=max_chars)
    return "\n".join(wrapped_lines) if wrapped_lines else text


def get_peter_image(emotion):
    """
    Get Peter's character image based on emotion.
    Quiz videos only use Peter.
    
    Args:
        emotion: "neutral", "angry", "excited", or "confused"
    
    Returns:
        Path to Peter's character image file
    """
    base_path = "assets/characters"
    
    if emotion == "neutral" or not emotion:
        return f"{base_path}/peter.png"
    else:
        return f"{base_path}/peter_{emotion}.png"


def create_quiz_video_with_audio_and_captions(
    background_video,
    audio_file,
    caption_timings,
    output_file="assets/output/quiz/final_quiz_video.mp4",
    video_size=(1080, 1920),  # Portrait 9:16 for TikTok/Reels
):
    """
    Create a quiz video with looping background, audio, caption overlays, and Peter's character.
    Quiz videos only use Peter as the narrator/host.
    
    Args:
        background_video: Path to background video (minecraft.mp4)
        audio_file: Path to audio file
        caption_timings: List of timing dictionaries with start, end, caption, speaker, emotion, is_pause
        output_file: Output video file path
        video_size: Tuple of (width, height) for output video
    
    Returns:
        Path to output video
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Check if audio file exists
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    
    # Build a list of unique Peter images needed for this video
    peter_images = {}  # {emotion: image_path}
    for timing in caption_timings:
        emotion = timing.get("emotion", "neutral")
        
        if emotion not in peter_images:
            image_path = get_peter_image(emotion)
            if os.path.exists(image_path):
                peter_images[emotion] = image_path
            else:
                # Fallback to neutral if emotion image doesn't exist
                fallback_path = get_peter_image("neutral")
                if os.path.exists(fallback_path):
                    print(f"⚠️  Warning: {image_path} not found, using neutral")
                    peter_images[emotion] = fallback_path
                else:
                    print(f"⚠️  Warning: Peter image not found: {image_path}")
                    peter_images[emotion] = None
    
    # Get audio duration
    duration_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_file
    ]
    result = subprocess.run(duration_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ ffprobe error: {result.stderr}")
        raise Exception(f"Failed to get audio duration: {result.stderr}")
    
    if not result.stdout.strip():
        print(f"❌ ffprobe returned empty output for: {audio_file}")
        print(f"   Command: {' '.join(duration_cmd)}")
        print(f"   stderr: {result.stderr}")
        raise ValueError(f"Could not determine audio duration for {audio_file}")
    
    audio_duration = float(result.stdout.strip())
    
    print(f"🎬 Creating quiz video with duration: {audio_duration:.2f}s")
    print(f"🎭 Peter emotions: {list(peter_images.keys())}")
    
    # Group timings by emotion for character overlay enable expressions
    def create_enable_expr(timings):
        if not timings:
            return "0"  # Never show
        conditions = [f"between(t,{t['start']},{t['end']})" for t in timings]
        return "+".join(conditions)
    
    # Create enable expressions for each Peter emotion
    peter_enables = {}
    for emotion in peter_images.keys():
        matching_timings = [
            t for t in caption_timings 
            if t.get("emotion", "neutral") == emotion and not t.get("is_pause", False)
        ]
        peter_enables[emotion] = create_enable_expr(matching_timings)
    
    # Build ffmpeg filter for captions (excluding pause indicators, but including options)
    caption_filters = []
    for timing in caption_timings:
        # Skip pause indicators in visual captions (but NOT options)
        if timing.get("is_pause", False):
            continue
        
        is_options = timing.get("is_options", False)
            
        # Wrap and escape caption text
        wrapped_text = wrap_caption_text(timing["caption"])
        
        caption_text = (
            wrapped_text
            .replace("\\", "\\\\")
            .replace("'", "'\\\\\\''")
            .replace(":", "\\:")
        )
        
        # Style based on whether it's options or regular caption
        if is_options:
            # Options: slightly smaller font, aligned left, different background
            color = "white"
            bg_color = "0x0000AA80"  # Blue tint for options
            fontsize = 48
            x_pos = "(w-tw)/2"  # Still centered but options take more space
            y_pos = "(h-th)/2"
        else:
            # Regular Peter caption style
            color = "white"
            bg_color = "0x00000080"
            fontsize = 54
            x_pos = "(w-tw)/2"
            y_pos = "(h-th)/2"
        
        # Create drawtext filter for this caption
        caption_filter = (
            f"drawtext=text='{caption_text}':"
            f"fontfile=/System/Library/Fonts/Supplemental/Arial Bold.ttf:"
            f"fontsize={fontsize}:"
            f"fontcolor={color}:"
            f"box=1:boxcolor={bg_color}:boxborderw=10:"
            f"x={x_pos}:" 
            f"y={y_pos}:" 
            f"text_align=C:"
            f"enable='between(t,{timing['start']},{timing['end']})':"
            f"line_spacing=18"
        )
        caption_filters.append(caption_filter)
    
    # Combine all caption filters
    all_captions = ",".join(caption_filters) if caption_filters else ""
    
    # Build filter_complex chain
    # Start with background video scaling
    filter_parts = [
        f"[0:v]scale={video_size[0]}:{video_size[1]}:force_original_aspect_ratio=decrease,"
        f"pad={video_size[0]}:{video_size[1]}:(ow-iw)/2:(oh-ih)/2[bg]"
    ]
    
    current_stream = "[bg]"
    input_index = 2  # 0=background, 1=audio, 2+=character images
    character_height = 480
    peter_margin = 10
    
    # Scale all Peter emotion images first
    peter_scaled_streams = {}
    for emotion, image_path in peter_images.items():
        if image_path:
            stream_name = f"peter_{emotion}_scaled"
            filter_parts.append(
                f"[{input_index}:v]scale=-1:{character_height}[{stream_name}]"
            )
            peter_scaled_streams[emotion] = f"[{stream_name}]"
            input_index += 1
    
    # Overlay Peter emotions on bottom right (quiz host position)
    overlay_count = 0
    for emotion in peter_images.keys():
        if emotion in peter_scaled_streams and peter_images[emotion]:
            enable_expr = peter_enables[emotion]
            filter_parts.append(
                f"{current_stream}{peter_scaled_streams[emotion]}"
                f"overlay=W-w-{peter_margin}:H-h-{peter_margin}:enable='{enable_expr}'[tmp_{overlay_count}]"
            )
            current_stream = f"[tmp_{overlay_count}]"
            overlay_count += 1
    
    # Add captions on top
    if all_captions:
        filter_parts.append(f"{current_stream}{all_captions}[v]")
    else:
        filter_parts.append(f"{current_stream}split[v]")
    
    filter_complex = ";".join(filter_parts)
    
    # Build ffmpeg command
    cmd = [
        "ffmpeg", "-y",
        # Input: Loop background video
        "-stream_loop", "-1",
        "-i", background_video,
        # Input: Audio
        "-i", audio_file,
    ]
    
    # Add all Peter image inputs in the same order as we used them in filter_parts
    for emotion, image_path in peter_images.items():
        if image_path:
            cmd.extend(["-loop", "1", "-i", image_path])
    
    # Add filter complex and output settings
    cmd.extend([
        # Video filters: scale, overlays, and captions
        "-filter_complex", filter_complex,
        # Map outputs
        "-map", "[v]",
        "-map", "1:a",
        # Set duration to match audio
        "-t", str(audio_duration),
        # Output settings
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        # Metadata
        "-movflags", "+faststart",
        output_file
    ])
    
    print(f"🎥 Rendering quiz video with {len([t for t in caption_timings if not t.get('is_pause')])} caption overlays...")
    print(f"   Background: {background_video}")
    print(f"   Audio: {audio_file}")
    
    # Run ffmpeg
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Quiz video created successfully: {output_file}")
        return output_file
    else:
        print(f"❌ Error creating quiz video:")
        print(result.stderr)
        raise Exception(f"FFmpeg failed with return code {result.returncode}")

def get_video_info(video_path):
    """Get video duration and other info using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=width,height,codec_name",
        "-of", "json",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

if __name__ == "__main__":
    # Example usage
    print("FFmpeg quiz video assembly module ready!")
    print("Use create_quiz_video_with_audio_and_captions() to generate quiz videos.")
    print("Quiz videos feature Peter as the quiz host.")
    
    # Example quiz caption timings:
    # quiz_timings = [
    #     {"start": 0.0, "end": 2.5, "caption": "Alright, time to test your knowledge!", "speaker": "PETER", "emotion": "excited", "is_pause": False},
    #     {"start": 2.5, "end": 5.0, "caption": "What is 2 + 2?", "speaker": "PETER", "emotion": "neutral", "is_pause": False},
    #     {"start": 5.0, "end": 7.0, "caption": "[Pause to think...]", "speaker": "PETER", "emotion": "neutral", "is_pause": True},
    #     {"start": 7.0, "end": 9.5, "caption": "The answer is 4!", "speaker": "PETER", "emotion": "excited", "is_pause": False},
    # ]
    # 
    # create_quiz_video_with_audio_and_captions(
    #     background_video="assets/background/minecraft.mp4",
    #     audio_file="assets/audio/quiz_full_audio.mp3",
    #     caption_timings=quiz_timings
    # )
