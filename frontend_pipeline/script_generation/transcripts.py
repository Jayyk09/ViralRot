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
        SubtopicDialogue,
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
        SubtopicDialogue,
    )
    from script_generation.youtube import get_youtube_transcript  # type: ignore


def _ensure_text(data):
    if isinstance(data, bytes):
        return data.decode("utf-8")
    return str(data)


def _extend_from_payload(payload: Any, subtopics: List[SubtopicDialogue]) -> bool:
    try:
        model = TranscriptResponse.model_validate(payload)
    except ValidationError:
        return False

    subtopics.extend(model.subtopic_transcripts)
    return True


def parse_transcript_json(json_input: str) -> List[SubtopicDialogue]:
    """
    Parse pre-formatted transcript JSON directly without Gemini processing.

    Accepts JSON in either format:
    1. Full format: {"subtopic_transcripts": [...]}
    2. Direct array: [{"subtopic_title": "...", "dialogue": [...]}]

    Args:
        json_input: JSON string matching the TranscriptResponse schema

    Returns:
        List of SubtopicDialogue objects

    Raises:
        ValueError: If JSON is invalid or doesn't match schema
    """
    try:
        data = json.loads(json_input)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")

    # Handle both formats
    if isinstance(data, list):
        # Direct array format
        data = {"subtopic_transcripts": data}

    try:
        response = TranscriptResponse.model_validate(data)
        return list(response.subtopic_transcripts)
    except ValidationError as e:
        raise ValueError(f"JSON doesn't match transcript schema: {e}")


def extract_transcripts(file, file_type):
    """
    Extract subtopic transcripts from various input types.

    Args:
        file: Input content (file path, text content, YouTube URL, or JSON string)
        file_type: One of 'audio/mp3', 'text', 'pptx', 'youtube', 'transcript'
            - audio/mp3: Path to audio file
            - text: Raw text content to be converted to dialogue
            - pptx: PowerPoint text content
            - youtube: YouTube URL or video ID
            - transcript: Pre-formatted JSON matching the schema (bypasses Gemini)

    Returns:
        List of SubtopicDialogue objects
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
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(inline_data=types.Blob(data=audio_b64, mime_type="audio/mp3")),
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

    subtopic_transcripts: List[SubtopicDialogue] = []
    accumulated_text = ""

    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        text = getattr(chunk, "text", None) or ""
        accumulated_text += text

        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict) and _extend_from_payload(parsed, subtopic_transcripts):
                break
        except Exception:
            pass

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
            if _extend_from_payload(resp_data, subtopic_transcripts):
                break

    if not subtopic_transcripts and accumulated_text:
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict):
                _extend_from_payload(parsed, subtopic_transcripts)
        except Exception:
            pass

    return subtopic_transcripts


if __name__ == "__main__":
    file = "C:\\Users\\Chris\\Downloads\\The essence of calculus.mp3"
    file_type = "audio/mp3"
    transcripts = extract_transcripts(file, file_type)
    for subtopic in transcripts:
        print(subtopic.model_dump())
