import base64
import os
import json
from typing import Any, List
from pathlib import Path

import dotenv
import google.genai as genai
import google.genai.types as types
from pydantic import ValidationError

try:
    from frontend_pipeline.script_generation.prompts import (
        AUDIO_PROMPT,
        TEXT_PROMPT,
        PPTX_PROMPT,
    )
    from frontend_pipeline.script_generation.models import (
        TranscriptResponse,
        SingleDialogue,
        SubtopicDialogue,  # Keep for backward compatibility
    )
    from frontend_pipeline.script_generation.youtube import get_youtube_transcript
except ImportError:  # pragma: no cover - fallback when run as script
    from script_generation.prompts import (  # type: ignore
        AUDIO_PROMPT,
        TEXT_PROMPT,
        PPTX_PROMPT,
    )
    from script_generation.models import (  # type: ignore
        TranscriptResponse,
        SingleDialogue,
        SubtopicDialogue,  # Keep for backward compatibility
    )
    from script_generation.youtube import get_youtube_transcript  # type: ignore


def _ensure_text(data):
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return str(data)


# =============================================================================
# Caption Splitting Utilities
# =============================================================================
# Automatically split long captions into 2 sequential dialogue lines for
# better on-screen readability.

CAPTION_SPLIT_THRESHOLD = 18  # Max words before auto-splitting


def _count_words(text: str) -> int:
    """Count words in a string."""
    return len(text.split())


def _split_caption_at_natural_break(text: str) -> tuple[str, str]:
    """
    Split caption at the most natural break point.
    
    Priority:
    1. Sentence boundaries (. ? !)
    2. Clause boundaries (, ; and but or)
    3. Closest space to midpoint
    
    Returns:
        Tuple of (part1, part2) where both are non-empty strings
    """
    # Try sentence boundaries first
    for delimiter in ['. ', '? ', '! ']:
        if delimiter in text:
            idx = text.find(delimiter) + len(delimiter)
            part1 = text[:idx].strip()
            part2 = text[idx:].strip()
            if part1 and part2:  # Ensure both parts have content
                return part1, part2
    
    # Try clause boundaries
    for delimiter in [', ', '; ', ' and ', ' but ', ' or ']:
        if delimiter in text:
            parts = text.split(delimiter, 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                # Keep delimiter with first part for natural flow
                return parts[0].strip() + delimiter.rstrip(), parts[1].strip()
    
    # Fall back to midpoint split
    words = text.split()
    mid = len(words) // 2
    part1 = ' '.join(words[:mid])
    part2 = ' '.join(words[mid:])
    return part1, part2


def _split_long_dialogue_line(line: dict, threshold: int = CAPTION_SPLIT_THRESHOLD) -> list[dict]:
    """
    Split a dialogue line if caption exceeds word threshold.
    
    Args:
        line: Dialogue line dict with caption, speaker, emotion, etc.
        threshold: Max words before splitting (default 18)
    
    Returns:
        List with 1 line (if under threshold) or 2 lines (if split)
    """
    caption = line.get("caption", "")
    word_count = _count_words(caption)
    
    # No split needed
    if word_count <= threshold:
        return [line]
    
    # Split caption at natural break
    part1, part2 = _split_caption_at_natural_break(caption)
    
    # Create first line
    line1 = {
        "caption": part1,
        "speaker": line["speaker"],
        "emotion": line["emotion"]
    }
    
    # Create second line
    line2 = {
        "caption": part2,
        "speaker": line["speaker"],
        "emotion": line["emotion"]
    }
    
    # Preserve images on BOTH parts (user preference)
    if "image" in line and line["image"]:
        line1["image"] = line["image"].copy() if isinstance(line["image"], dict) else line["image"]
        line2["image"] = line["image"].copy() if isinstance(line["image"], dict) else line["image"]
    
    if "images" in line and line["images"]:
        line1["images"] = [img.copy() if isinstance(img, dict) else img for img in line["images"]]
        line2["images"] = [img.copy() if isinstance(img, dict) else img for img in line["images"]]
    
    # Estimate duration proportionally based on word count
    if "duration_estimate" in line:
        total_duration = line["duration_estimate"]
        words1 = _count_words(part1)
        words2 = _count_words(part2)
        total_words = words1 + words2
        
        line1["duration_estimate"] = (words1 / total_words) * total_duration
        line2["duration_estimate"] = (words2 / total_words) * total_duration
    
    return [line1, line2]


def _apply_caption_splitting(dialogue: "SingleDialogue") -> "SingleDialogue":
    """
    Apply caption splitting to all dialogue lines that exceed the threshold.
    
    Args:
        dialogue: SingleDialogue object from Gemini
    
    Returns:
        SingleDialogue with long captions split into multiple lines
    """
    if not dialogue.dialogue:
        return dialogue
    
    # Process each line
    processed_lines = []
    split_count = 0
    
    for line in dialogue.dialogue:
        # Convert Pydantic model to dict for processing
        line_dict = line.model_dump() if hasattr(line, 'model_dump') else dict(line)
        split_lines = _split_long_dialogue_line(line_dict)
        processed_lines.extend(split_lines)
        if len(split_lines) > 1:
            split_count += 1
    
    # Log splitting stats
    if split_count > 0:
        print(f"✂️  Auto-split {split_count} long caption(s) for better readability")
        print(f"   Total dialogue lines: {len(dialogue.dialogue)} → {len(processed_lines)}")
    
    # Create new SingleDialogue with processed lines
    # Import here to avoid circular imports
    from frontend_pipeline.script_generation.models import SingleDialogue as SD, DialogueLine
    
    # Convert dicts back to DialogueLine objects
    new_lines = [DialogueLine(**line_dict) for line_dict in processed_lines]
    
    return SD(
        title=dialogue.title,
        dialogue=new_lines
    )


def _extract_dialogue_from_payload(payload: Any) -> SingleDialogue | None:
    """Extract SingleDialogue from Gemini response payload."""
    try:
        model = TranscriptResponse.model_validate(payload)
        return model.dialogue_data
    except ValidationError:
        return None


def _extend_from_payload_legacy(payload: Any, subtopics: List[SubtopicDialogue]) -> bool:
    """DEPRECATED: Legacy function for backward compatibility with old multi-subtopic format."""
    try:
        # Try to parse as old format with subtopic_transcripts
        if isinstance(payload, dict) and "subtopic_transcripts" in payload:
            for subtopic_data in payload["subtopic_transcripts"]:
                subtopic = SubtopicDialogue.model_validate(subtopic_data)
                subtopics.append(subtopic)
            return True
    except ValidationError:
        pass
    return False


def parse_transcript_json(json_input: str) -> SingleDialogue:
    """
    Parse pre-formatted transcript JSON directly without Gemini processing.

    Accepts JSON in the new format:
    {"dialogue_data": {"title": "...", "dialogue": [...]}}

    Args:
        json_input: JSON string matching the TranscriptResponse schema

    Returns:
        SingleDialogue object (with long captions auto-split)

    Raises:
        ValueError: If JSON is invalid or doesn't match schema
    """
    try:
        data = json.loads(json_input)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    try:
        response = TranscriptResponse.model_validate(data)
        dialogue = response.dialogue_data
        # Apply caption splitting for long captions
        return _apply_caption_splitting(dialogue)
    except ValidationError as e:
        raise ValueError(f"JSON doesn't match transcript schema: {e}")


def extract_transcripts(file, file_type) -> SingleDialogue:
    """
    Extract a single dialogue from various input types.

    Args:
        file: Input content (file path, text content, YouTube URL, or JSON string)
        file_type: One of 'audio/mp3', 'text', 'pptx', 'youtube', 'transcript'
            - audio/mp3: Path to audio file
            - text: Raw text content to be converted to dialogue
            - pptx: PowerPoint text content
            - youtube: YouTube URL or video ID
            - transcript: Pre-formatted JSON matching the schema (bypasses Gemini)

    Returns:
        SingleDialogue object
    """
    # Handle pre-formatted transcript JSON directly (no Gemini)
    if file_type == "transcript":
        json_input = _ensure_text(file)
        return parse_transcript_json(json_input)

    dotenv.load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)
    model = "gemini-2.5-flash"

    if file_type == "audio/mp3":
        if not os.path.isfile(file):
            raise FileNotFoundError(f"Audio file not found: {file}")
        with open(file, "rb") as f:
            audio_bytes = f.read()
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(inline_data=types.Blob(data=audio_bytes, mime_type="audio/mp3")),
                ],
            ),
        ]
        prompt = [
            types.Part.from_text(text=AUDIO_PROMPT),
        ]
    elif file_type == "text":
        text_data = _ensure_text(file)
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=text_data),
                ],
            ),
        ]
        prompt = [
            types.Part.from_text(text=TEXT_PROMPT),
        ]
    elif file_type == "youtube":
        # Fetch transcript from YouTube and process as text
        youtube_transcript = get_youtube_transcript(file)
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=youtube_transcript),
                ],
            ),
        ]
        prompt = [
            types.Part.from_text(text=TEXT_PROMPT),
        ]
    elif file_type == "pptx":
        pptx_data = _ensure_text(file)
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=pptx_data),
                ],
            ),
        ]
        prompt = [
            types.Part.from_text(text=PPTX_PROMPT)
        ]
    else:
        raise ValueError(f"Unsupported file_type: {file_type}. Use 'audio/mp3', 'text', 'pptx', 'youtube', or 'transcript'.")

    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_budget=0,
        ),
        image_config=types.ImageConfig(
            image_size="1K",
        ),
        response_mime_type="application/json",
        response_schema=TranscriptResponse.model_json_schema(),
        system_instruction=prompt
    )

    dialogue_result: SingleDialogue | None = None
    accumulated_text = ""

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        text = getattr(chunk, "text", None) or ""
        accumulated_text += text

        # Try to parse accumulated text
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict):
                dialogue = _extract_dialogue_from_payload(parsed)
                if dialogue:
                    dialogue_result = dialogue
                    break
        except Exception:
            pass

        # Try to extract from chunk response data
        resp_data = None
        if hasattr(chunk, "response") and getattr(chunk, "response"):
            resp = getattr(chunk, "response")
            if hasattr(resp, "data") and getattr(resp, "data"):
                resp_data = getattr(resp, "data")

        if resp_data is None:
            try:
                dumped = chunk.model_dump()
            except Exception:
                dumped = getattr(chunk, "__dict__", None)

            if isinstance(dumped, dict):
                if "response" in dumped and isinstance(dumped["response"], dict):
                    resp_data = dumped["response"].get("data")
                elif "data" in dumped and dumped["data"]:
                    resp_data = dumped["data"]
                elif "outputs" in dumped and dumped["outputs"]:
                    for out in dumped["outputs"]:
                        if isinstance(out, dict) and "data" in out and out["data"]:
                            resp_data = out["data"]
                            break

        if resp_data and isinstance(resp_data, dict):
            dialogue = _extract_dialogue_from_payload(resp_data)
            if dialogue:
                dialogue_result = dialogue
                break

    # Final attempt to parse accumulated text
    if not dialogue_result and accumulated_text:
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict):
                dialogue_result = _extract_dialogue_from_payload(parsed)
        except Exception:
            pass

    if not dialogue_result:
        raise ValueError("Failed to extract dialogue from Gemini response")

    # Apply caption splitting for long captions (>18 words)
    dialogue_result = _apply_caption_splitting(dialogue_result)

    return dialogue_result


if __name__ == "__main__":
    file = "C:\\Users\\Chris\\Downloads\\The essence of calculus.mp3"
    file_type = "audio/mp3"
    dialogue = extract_transcripts(file, file_type)
    print(dialogue.model_dump())
