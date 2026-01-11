import subprocess
import os
import textwrap

def wrap_caption_text(text, max_chars=32):
    """Wrap caption text to a maximum characters per line (word-aware)."""
    wrapped_lines = textwrap.wrap(text, width=max_chars)
    return "\n".join(wrapped_lines) if wrapped_lines else text


def get_character_image(speaker, emotion):
    """
    Get the character image path based on speaker and emotion.
    
    Args:
        speaker: "PETER" or "STEWIE"
        emotion: "neutral", "angry", "excited", or "confused"
    
    Returns:
        Path to the character image file
    """
    base_path = "assets/characters"
    speaker_lower = speaker.lower()
    
    # Map emotion to image file
    if emotion == "neutral" or not emotion:
        return f"{base_path}/{speaker_lower}.png"
    else:
        return f"{base_path}/{speaker_lower}_{emotion}.png"


def create_video_with_audio_and_captions(
    background_video,
    audio_file,
    caption_timings,
    output_file="assets/output/final_video.mp4",
    video_size=(1080, 1920),  # Portrait 9:16 for TikTok/Reels
    peter_image=None,  # Deprecated, kept for backward compatibility
    stewie_image=None,  # Deprecated, kept for backward compatibility
    educational_images=None,  # List of educational image configs
):
    """
    Create a video with looping background, audio, caption overlays, and character images.
    
    Args:
        background_video: Path to background video (minecraft.mp4)
        audio_file: Path to audio file
        caption_timings: List of timing dictionaries with start, end, caption, speaker, emotion
        output_file: Output video file path
        video_size: Tuple of (width, height) for output video
        peter_image: Deprecated - images now selected based on emotion
        stewie_image: Deprecated - images now selected based on emotion
        educational_images: List of educational image configs with:
            - path: Image file path
            - size: "medium" (432px) or "large" (800px)
            - start: Start time in seconds
            - end: End time in seconds
    
    Returns:
        Path to output video
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Check if audio file exists
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    
    # Build a list of unique character images needed for this video
    character_images = {}  # {(speaker, emotion): image_path}
    for timing in caption_timings:
        speaker = timing["speaker"]
        emotion = timing.get("emotion", "neutral")
        key = (speaker, emotion)
        
        if key not in character_images:
            image_path = get_character_image(speaker, emotion)
            if os.path.exists(image_path):
                character_images[key] = image_path
            else:
                # Fallback to neutral if emotion image doesn't exist
                fallback_path = get_character_image(speaker, "neutral")
                if os.path.exists(fallback_path):
                    print(f"⚠️  Warning: {image_path} not found, using neutral")
                    character_images[key] = fallback_path
                else:
                    print(f"⚠️  Warning: Character image not found: {image_path}")
                    character_images[key] = None
    
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
    
    print(f"🎬 Creating video with duration: {audio_duration:.2f}s")
    print(f"🎭 Character emotions: {list(character_images.keys())}")
    
    # Group timings by (speaker, emotion) for character overlay enable expressions
    def create_enable_expr(timings):
        if not timings:
            return "0"  # Never show
        conditions = [f"between(t,{t['start']},{t['end']})" for t in timings]
        return "+".join(conditions)
    
    # Create enable expressions for each character-emotion combination
    character_enables = {}
    for key in character_images.keys():
        speaker, emotion = key
        matching_timings = [
            t for t in caption_timings 
            if t["speaker"] == speaker and t.get("emotion", "neutral") == emotion
        ]
        character_enables[key] = create_enable_expr(matching_timings)
    
    # Build ffmpeg filter for captions
    caption_filters = []
    for timing in caption_timings:
        # Wrap and escape caption text
        wrapped_text = wrap_caption_text(timing["caption"])
        
        # The \n from textwrap should be passed to ffmpeg as a literal newline
        caption_text = (
            wrapped_text
            .replace("\\", "\\\\")
            .replace("'", "'\\\\\\''")
            .replace(":", "\\:")
        )
        speaker = timing["speaker"]
        
        # Style for captions
        if speaker == "PETER":
            color = "white"
            bg_color = "0x00000080"  
        else:
            color = "yellow"
            bg_color = "0x0000FF80"  
        
        # Create drawtext filter for this caption with manual wrapping
        caption_filter = (
            f"drawtext=text='{caption_text}':"
            f"fontfile=/System/Library/Fonts/Supplemental/Arial Bold.ttf:"
            f"fontsize=54:"
            f"fontcolor={color}:"
            f"box=1:boxcolor={bg_color}:boxborderw=10:"
            f"x=(w-tw)/2:" 
            f"y=(h-th)/2:" 
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
    character_height = 800
    peter_margin = 0   # Both characters now on left side
    stewie_margin = 0  # Both characters now on left side
    
    # Scale all character images first
    character_scaled_streams = {}
    for key, image_path in character_images.items():
        if image_path:
            speaker, emotion = key
            stream_name = f"{speaker.lower()}_{emotion}_scaled"
            filter_parts.append(
                f"[{input_index}:v]scale=-1:{character_height}[{stream_name}]"
            )
            character_scaled_streams[key] = f"[{stream_name}]"
            input_index += 1
    
    # Overlay characters in order: Both on bottom-left (right side free for images)
    # Group by speaker to maintain consistent positioning
    stewie_keys = [k for k in character_images.keys() if k[0] == "STEWIE"]
    peter_keys = [k for k in character_images.keys() if k[0] == "PETER"]
    
    overlay_count = 0
    
    # Overlay all Stewie emotions on bottom left
    for key in stewie_keys:
        if key in character_scaled_streams and character_images[key]:
            enable_expr = character_enables[key]
            filter_parts.append(
                f"{current_stream}{character_scaled_streams[key]}"
                f"overlay={stewie_margin}:H-h-{stewie_margin}:enable='{enable_expr}'[tmp_{overlay_count}]"
            )
            current_stream = f"[tmp_{overlay_count}]"
            overlay_count += 1
    
    # Overlay all Peter emotions on bottom left (same side as Stewie)
    for key in peter_keys:
        if key in character_scaled_streams and character_images[key]:
            enable_expr = character_enables[key]
            filter_parts.append(
                f"{current_stream}{character_scaled_streams[key]}"
                f"overlay={peter_margin}:H-h-{peter_margin}:enable='{enable_expr}'[tmp_{overlay_count}]"
            )
            current_stream = f"[tmp_{overlay_count}]"
            overlay_count += 1
    
    # ============ Educational Images Overlay ============
    # Scale and overlay educational images with fade effects
    # Image sizes: medium=432px wide, large=800px wide
    # Positions: medium=top-right, large=top-center
    # Fade: 0.3s fade in/out
    
    edu_images = educational_images or []
    edu_scaled_streams = []
    edu_input_start_index = input_index  # Track where edu images start in inputs
    
    FADE_DURATION = 0.3  # seconds for fade in/out
    IMAGE_SIZES = {
        "medium": 432,
        "large": 800,
    }
    
    # Scale educational images
    for i, edu_img in enumerate(edu_images):
        if not os.path.exists(edu_img["path"]):
            print(f"⚠️  Warning: Educational image not found: {edu_img['path']}")
            continue
        
        size_name = edu_img.get("size", "medium")
        width = IMAGE_SIZES.get(size_name, IMAGE_SIZES["medium"])
        
        stream_name = f"edu_{i}_scaled"
        filter_parts.append(
            f"[{input_index}:v]scale={width}:-1[{stream_name}]"
        )
        edu_scaled_streams.append({
            "stream": f"[{stream_name}]",
            "size": size_name,
            "start": edu_img["start"],
            "end": edu_img["end"],
            "path": edu_img["path"],
        })
        input_index += 1
    
    # Overlay educational images with positioning and fade
    for i, edu_stream in enumerate(edu_scaled_streams):
        start = edu_stream["start"]
        end = edu_stream["end"]
        duration = end - start
        size_name = edu_stream["size"]
        
        # Positioning based on size
        # medium: top-right with 50px margin
        # large: top-center
        if size_name == "large":
            x_pos = "(W-w)/2"  # Center horizontally
        else:  # medium
            x_pos = "W-w-50"   # Right side with 50px margin
        
        y_pos = "100"  # 100px from top
        
        # Fade expression: fade in for first 0.3s, fade out for last 0.3s
        fade_in_end = start + FADE_DURATION
        fade_out_start = max(end - FADE_DURATION, fade_in_end)
        
        # Alpha expression for overlay - fade in then out
        # Clamp values between 0 and 1
        alpha_expr = (
            f"if(lt(t,{start}),0,"
            f"if(lt(t,{fade_in_end}),min(1,(t-{start})/{FADE_DURATION}),"
            f"if(lt(t,{fade_out_start}),1,"
            f"if(lt(t,{end}),max(0,({end}-t)/{FADE_DURATION}),"
            f"0))))"
        )
        
        # Use format=auto for overlay with alpha channel
        filter_parts.append(
            f"{current_stream}{edu_stream['stream']}"
            f"overlay=x={x_pos}:y={y_pos}:alpha='{alpha_expr}'[tmp_{overlay_count}]"
        )
        current_stream = f"[tmp_{overlay_count}]"
        overlay_count += 1
    
    if edu_images:
        print(f"📷 Added {len(edu_scaled_streams)} educational image overlays")
    
    # Add captions on top
    if all_captions:
        filter_parts.append(f"{current_stream}{all_captions}[v]")
    else:
        filter_parts.append(f"{current_stream}split[v]") # Use split to ensure a named output stream even if no captions
    
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
    
    # Add all character image inputs in the same order as we used them in filter_parts
    # The order here must match the order in which we created the scaled streams
    for key, image_path in character_images.items():
        if image_path:
            cmd.extend(["-loop", "1", "-i", image_path])
    
    # Add educational image inputs
    for edu_stream in edu_scaled_streams:
        cmd.extend(["-loop", "1", "-i", edu_stream["path"]])
    
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
    
    print(f"🎥 Rendering video with {len(caption_timings)} caption overlays...")
    print(f"   Background: {background_video}")
    print(f"   Audio: {audio_file}")
    
    # Run ffmpeg
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Video created successfully: {output_file}")
        return output_file
    else:
        print(f"❌ Error creating video:")
        print(result.stderr)
        raise Exception(f"FFmpeg failed with return code {result.returncode}")

if __name__ == "__main__":
    # Example usage
    print("FFmpeg video assembly module ready!")
    print("Use create_video_with_audio_and_captions() to generate videos.")

    # You would need to add your actual assets and timings here to run it
    # example_timings = [
    #     {"start": 1.0, "end": 3.5, "caption": "This is a very long caption that should definitely wrap and be centered", "speaker": "PETER"},
    #     {"start": 4.0, "end": 6.0, "caption": "And this is Stewie speaking from his side of the screen", "speaker": "STEWIE"},
    # ]
    # 
    # create_video_with_audio_and_captions(
    #     background_video="assets/background/minecraft.mp4",
    #     audio_file="assets/audio/my_audio.mp3",
    #     caption_timings=example_timings
    # )