"""YouTube transcript extraction using youtube-transcript-api."""
import re
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


def extract_video_id(url: str) -> str:
    """
    Extract video ID from various YouTube URL formats.
    
    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://m.youtube.com/watch?v=VIDEO_ID
    
    Args:
        url: YouTube URL or video ID
        
    Returns:
        11-character video ID
        
    Raises:
        ValueError: If video ID cannot be extracted
    """
    # If it's already a video ID (11 alphanumeric characters with _ or -)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    # Try multiple URL patterns
    patterns = [
        r'(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:m\.youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError(
        f"Could not extract video ID from URL: {url}. "
        "Expected format: youtube.com/watch?v=VIDEO_ID or youtu.be/VIDEO_ID"
    )


def get_youtube_transcript(url: str, languages: Optional[list] = None) -> str:
    """
    Fetch transcript text from a YouTube video.
    
    Args:
        url: YouTube URL or video ID
        languages: List of language codes to try (default: ['en'])
        
    Returns:
        Combined transcript text as a single string
        
    Raises:
        ValueError: If video ID is invalid, transcripts are disabled, 
                   or no transcript found in requested language
    """
    if languages is None:
        languages = ['en']
    
    video_id = extract_video_id(url)
    
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    except TranscriptsDisabled:
        raise ValueError(
            f"Transcripts are disabled for video: {url}. "
            "This video may have captions turned off by the uploader."
        )
    except NoTranscriptFound:
        lang_str = ", ".join(languages)
        raise ValueError(
            f"No transcript found in languages [{lang_str}] for video: {url}. "
            "Try a video with English captions enabled."
        )
    except Exception as e:
        raise ValueError(f"Failed to fetch transcript for video: {url}. Error: {str(e)}")
    
    # Combine all transcript entries into a single text string
    return " ".join([entry['text'] for entry in transcript_list])
