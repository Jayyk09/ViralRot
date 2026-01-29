"""
ASS (Advanced SubStation Alpha) subtitle generator for karaoke-style captions.

Generates ASS files with karaoke timing tags (\\k) that highlight words
as they're being spoken - white text turning yellow word by word.
"""

import os
import tempfile
from typing import List, Dict, Any, Optional


def format_ass_time(seconds: float) -> str:
    """
    Convert seconds to ASS time format (H:MM:SS.CC).
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string like "0:00:05.23"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def split_caption_into_chunks(caption_text: str, max_words: int = 5) -> List[str]:
    """
    Split caption into chunks of max_words each.
    
    Args:
        caption_text: The caption text to split
        max_words: Maximum words per chunk (default 5)
        
    Returns:
        List of caption chunks (each chunk is a string)
    """
    if not caption_text:
        return []
    
    words = caption_text.split()
    chunks = []
    
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i:i+max_words])
        chunks.append(chunk)
    
    return chunks


def calculate_chunk_timings(
    caption_text: str,
    start_time: float,
    end_time: float,
    max_words_per_chunk: int = 5
) -> List[Dict[str, Any]]:
    """
    Split caption into chunks and calculate timing for each chunk.
    
    Distributes the total caption duration across chunks proportionally
    based on character count in each chunk.
    
    Args:
        caption_text: The caption text to split
        start_time: Start time of the caption in seconds
        end_time: End time of the caption in seconds
        max_words_per_chunk: Maximum words per chunk (default 5)
        
    Returns:
        List of dicts with 'text', 'start', and 'end' keys
    """
    if not caption_text:
        return []
    
    chunks = split_caption_into_chunks(caption_text, max_words_per_chunk)
    if not chunks:
        return []
    
    total_duration = end_time - start_time
    
    # Calculate character count for each chunk
    chunk_chars = [len(chunk) for chunk in chunks]
    total_chars = sum(chunk_chars)
    
    if total_chars == 0:
        return []
    
    # Distribute duration proportionally
    chunk_timings = []
    current_time = start_time
    
    for i, chunk in enumerate(chunks):
        # Calculate duration for this chunk based on character count
        char_ratio = chunk_chars[i] / total_chars
        chunk_duration = total_duration * char_ratio
        
        # Ensure minimum duration of 0.5s per chunk for readability
        chunk_duration = max(0.5, chunk_duration)
        
        chunk_end = current_time + chunk_duration
        
        chunk_timings.append({
            "text": chunk,
            "start": current_time,
            "end": min(chunk_end, end_time),  # Don't exceed original end time
        })
        
        current_time = chunk_end
    
    # Adjust last chunk to exactly match end_time
    if chunk_timings:
        chunk_timings[-1]["end"] = end_time
    
    return chunk_timings


def calculate_word_timings(
    caption_text: str,
    start_time: float,
    end_time: float,
    method: str = "proportional"
) -> List[Dict[str, Any]]:
    """
    Calculate timing for each word in a caption.
    
    Distributes the caption duration across words, either evenly or
    proportionally based on word length.
    
    Args:
        caption_text: The caption text to split into words
        start_time: Start time of the caption in seconds
        end_time: End time of the caption in seconds
        method: "even" for equal time per word, "proportional" for length-based
        
    Returns:
        List of dicts with 'word' and 'duration_cs' (centiseconds) keys
    """
    if caption_text is None:
        print(f"⚠️  WARNING: caption_text is None in calculate_word_timings")
        return []

    words = caption_text.split()
    if not words:
        return []
    
    duration = end_time - start_time
    
    if method == "even":
        # Equal time for each word
        time_per_word = duration / len(words)
        return [
            {"word": word, "duration_cs": max(1, int(time_per_word * 100))}
            for word in words
        ]
    else:
        # Proportional by word length (more natural)
        total_chars = sum(len(w) for w in words)
        if total_chars == 0:
            return [{"word": w, "duration_cs": 10} for w in words]
        
        timings = []
        for word in words:
            word_ratio = len(word) / total_chars
            word_duration = duration * word_ratio
            # Minimum 10 centiseconds (0.1s) per word for readability
            timings.append({
                "word": word,
                "duration_cs": max(10, int(word_duration * 100))
            })
        return timings


def escape_ass_text(text: str) -> str:
    """
    Escape special characters for ASS format.
    
    Args:
        text: Raw text to escape
        
    Returns:
        Escaped text safe for ASS files
    """
    # ASS uses \n for newlines, \N for hard line breaks
    # Backslashes and curly braces need escaping in some contexts
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def create_ass_header(
    title: str = "Educational Video Captions",
    video_width: int = 1080,
    video_height: int = 1920,
    font_name: str = "Arial Bold",
    font_size: int = 48,
) -> str:
    """
    Create the ASS file header with script info and styles.
    
    Defines a karaoke style where:
    - Primary color: White (unspoken words)
    - Secondary color: Yellow (currently being spoken)
    - No background box (transparent)
    - Centered at middle of screen
    
    Args:
        title: Script title
        video_width: Video width for scaling
        video_height: Video height for scaling
        font_name: Font to use
        font_size: Font size in pixels
        
    Returns:
        ASS header string
    """
    # ASS colors are in &HAABBGGRR format (Alpha, Blue, Green, Red)
    # &H00FFFFFF = White (fully opaque)
    # &H0000FFFF = Yellow (BGR: 00, FF, FF = Yellow)
    # &H00000000 = Black (for outline)
    # &H80000000 = Semi-transparent black (for shadow)
    
    primary_color = "&H00FFFFFF"      # White - unspoken text
    secondary_color = "&H0000FFFF"    # Yellow - karaoke highlight
    outline_color = "&H00000000"      # Black outline for readability
    back_color = "&H00000000"         # Transparent background
    
    # Style format:
    # Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour,
    # Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,
    # BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
    #
    # BorderStyle: 1 = outline + shadow, 3 = opaque box
    # Alignment: 2 = bottom-center, 5 = middle-center, 8 = top-center
    # Using 5 for middle-center to match current caption positioning
    
    header = f"""[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,3,1,5,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header


def create_dialogue_line(
    start_time: float,
    end_time: float,
    text: str,
    style: str = "Karaoke",
    word_timings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Create a single ASS dialogue line with karaoke tags.
    
    Args:
        start_time: Start time in seconds
        end_time: End time in seconds
        text: Caption text
        style: ASS style name to use
        word_timings: Pre-calculated word timings, or None to calculate
        
    Returns:
        Formatted ASS dialogue line
    """
    start_str = format_ass_time(start_time)
    end_str = format_ass_time(end_time)
    
    # Calculate word timings if not provided
    if word_timings is None:
        word_timings = calculate_word_timings(text, start_time, end_time)
    
    # Build karaoke text with \k tags
    # \kf = smooth fill effect (looks better than basic \k)
    karaoke_parts = []
    for timing in word_timings:
        word = escape_ass_text(timing["word"])
        duration = timing["duration_cs"]
        karaoke_parts.append(f"{{\\kf{duration}}}{word}")
    
    karaoke_text = " ".join(karaoke_parts)
    
    # Dialogue format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    return f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{karaoke_text}"


def generate_ass_subtitle_file(
    caption_timings: List[Dict[str, Any]],
    output_path: Optional[str] = None,
    title: str = "Educational Video Captions",
    video_size: tuple = (1080, 1920),
    font_name: str = "Arial Bold",
    font_size: int = 48,
    timing_method: str = "proportional",
    max_words_per_chunk: int = 5,
) -> str:
    """
    Generate a complete ASS subtitle file with karaoke-style captions.
    
    Creates an ASS file where words highlight in yellow as they're
    spoken, with white text for words not yet spoken.
    
    Captions are automatically split into chunks of max_words_per_chunk
    to keep text concise and readable on screen.
    
    Args:
        caption_timings: List of caption timing dicts with:
            - caption: Text to display
            - start: Start time in seconds
            - end: End time in seconds
            - speaker: "PETER" or "STEWIE" (currently unused, for future styling)
        output_path: Path to save ASS file, or None for temp file
        title: Script title
        video_size: Tuple of (width, height)
        font_name: Font to use
        font_size: Font size
        timing_method: "even" or "proportional" for word timing distribution
        max_words_per_chunk: Maximum words to show on screen at once (default 5)
        
    Returns:
        Path to generated ASS file
    """
    # Create output path if not provided
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".ass", prefix="karaoke_")
        os.close(fd)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    # Generate header
    header = create_ass_header(
        title=title,
        video_width=video_size[0],
        video_height=video_size[1],
        font_name=font_name,
        font_size=font_size,
    )
    
    # Generate dialogue lines
    print(f"\n🔍 ASS GENERATOR - Processing {len(caption_timings) if caption_timings else 0} captions")
    print(f"   Chunking: Max {max_words_per_chunk} words per screen")
    dialogue_lines = []
    
    for i, timing in enumerate(caption_timings or []):
        caption_text = timing.get("caption") or ""  # Handle None value
        start = timing.get("start", 0)
        end = timing.get("end", 0)

        # Debug log for first few and any problematic entries
        if i < 3 or caption_text is None:
            print(f"  [{i}] caption={caption_text[:30] if caption_text else 'None/Empty'}... start={start} end={end}")

        if not caption_text or end <= start:
            continue
        
        # Split caption into chunks with calculated timings
        chunk_timings = calculate_chunk_timings(
            caption_text, start, end, max_words_per_chunk=max_words_per_chunk
        )
        
        # Create dialogue line for each chunk
        for chunk_idx, chunk in enumerate(chunk_timings):
            chunk_text = chunk["text"]
            chunk_start = chunk["start"]
            chunk_end = chunk["end"]
            
            # Calculate word timings within this chunk
            word_timings = calculate_word_timings(
                chunk_text, chunk_start, chunk_end, method=timing_method
            )
            
            # Create dialogue line
            line = create_dialogue_line(
                start_time=chunk_start,
                end_time=chunk_end,
                text=chunk_text,
                word_timings=word_timings,
            )
            dialogue_lines.append(line)
            
            # Debug log for first few chunks
            if i < 2:
                print(f"    Chunk {chunk_idx+1}: '{chunk_text[:40]}...' ({chunk_start:.2f}s - {chunk_end:.2f}s)")
    
    # Write file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for line in dialogue_lines:
            f.write(line + "\n")
    
    print(f"✅ Generated ASS file with {len(dialogue_lines)} dialogue chunks")
    
    return output_path


# Quick test when run directly
if __name__ == "__main__":
    # Example caption timings
    test_timings = [
        {
            "caption": "Hey Stewie, you ever wonder how plants make food?",
            "start": 0.0,
            "end": 3.5,
            "speaker": "PETER",
        },
        {
            "caption": "It's called photosynthesis, you simpleton.",
            "start": 3.7,
            "end": 7.0,
            "speaker": "STEWIE",
        },
        {
            "caption": "Plants use sunlight to convert water and carbon dioxide into sugar!",
            "start": 7.2,
            "end": 12.0,
            "speaker": "PETER",
        },
    ]
    
    # Generate test file
    output = generate_ass_subtitle_file(
        test_timings,
        output_path="tmp/test_karaoke.ass",
    )
    
    print(f"Generated ASS file: {output}")
    print("\nContents:")
    with open(output, "r") as f:
        print(f.read())
