import base64
import os
import json
from typing import Any, List
from pathlib import Path

import http.client

import dotenv
import google.genai as genai
import google.genai.types as types
from pydantic import ValidationError

try:
    from frontend_pipeline.script_generation.prompts import (
        AUDIO_PROMPT,
        TEXT_PROMPT,
        PPTX_PROMPT,
        AUDIO_QUIZ_PROMPT,
        TEXT_QUIZ_PROMPT,
        PPTX_QUIZ_PROMPT,
    )
    from frontend_pipeline.script_generation.models import (
        TranscriptResponse,
        SubtopicDialogue,
        QuizResponse,
        QuizModule,
    )
except ImportError:  # pragma: no cover - fallback when run as script
    from script_generation.prompts import (  # type: ignore
        AUDIO_PROMPT,
        TEXT_PROMPT,
        PPTX_PROMPT,
        AUDIO_QUIZ_PROMPT,
        TEXT_QUIZ_PROMPT,
        PPTX_QUIZ_PROMPT,
    )
    from script_generation.models import (  # type: ignore
        TranscriptResponse,
        SubtopicDialogue,
        QuizResponse,
        QuizModule,
    )


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


def _extend_from_quiz_payload(payload: Any, quiz_modules: List[QuizModule]) -> bool:
    try:
        model = QuizResponse.model_validate(payload)
    except ValidationError:
        return False

    quiz_modules.extend(model.quiz_modules)
    return True

def extract_audio_from_youtube(url):
    """
    Extract audio from YouTube URL using RapidAPI yt-downloader9.
    
    Returns:
        Audio file bytes
    """
    import time
    
    dotenv.load_dotenv()
    api_key = os.getenv("RapidAPI_Key")
    if not api_key:
        raise ValueError("RapidAPI_Key not set")
    
    conn = http.client.HTTPSConnection("yt-downloader9.p.rapidapi.com")
    
    headers = {
        'x-rapidapi-key': api_key,
        'x-rapidapi-host': "yt-downloader9.p.rapidapi.com",
        'Content-Type': "application/json"
    }
    
    # Step 1: Start download
    payload = json.dumps({
        "urls": [url],
        "onlyAudio": True,
        "ignorePlaylists": True,
        "videoQuality": "hd"
    })
    
    conn.request("POST", "/start", payload, headers)
    res = conn.getresponse()
    data = res.read()
    start_response = json.loads(data.decode("utf-8"))
    
    if "uid" not in start_response:
        raise ValueError(f"Failed to start download: {start_response}")
    
    uid = start_response["uid"]
    print(f"Download started with UID: {uid}")
    
    # Step 2: Poll for status until READY or DONE
    max_retries = 120  # 10 minutes max (5 second intervals)
    retry_count = 0
    start_time = time.time()
    
    while retry_count < max_retries:
        time.sleep(5)  # Wait 5 seconds between checks
        retry_count += 1
        elapsed = int(time.time() - start_time)
        
        conn = http.client.HTTPSConnection("yt-downloader9.p.rapidapi.com")
        conn.request("GET", f"/status/{uid}", headers=headers)
        res = conn.getresponse()
        data = res.read()
        status_response = json.loads(data.decode("utf-8"))
        
        status = status_response.get("status")
        print(f"[{elapsed}s] Status: {status} (attempt {retry_count}/{max_retries})")
        
        if status == "READY" or status == "DONE":
            target_file = status_response.get("targetFile")
            print(f"Download ready: {target_file}")
            
            # Step 3: Download the file and return bytes
            conn = http.client.HTTPSConnection("yt-downloader9.p.rapidapi.com")
            conn.request("GET", f"/download/{uid}", headers=headers)
            res = conn.getresponse()
            audio_bytes = res.read()
            
            print(f"Audio downloaded: {len(audio_bytes)} bytes")
            return audio_bytes
        
        elif status == "YOUTUBE-ERROR" or status == "CANCELED":
            raise ValueError(f"Download failed with status: {status}")
    
    # If we get here, we've exceeded max retries
    total_time = max_retries * 5
    raise TimeoutError(f"Download timed out after {total_time} seconds ({total_time // 60} minutes)")

def extract_transcripts(file, file_type):
    dotenv.load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    
    client = genai.Client(api_key=api_key)

    model = "gemini-2.5-flash"

    # Read the audio file and provide base64-encoded data to the Blob.
    #if not os.path.isfile(audio_file_path):
        #raise FileNotFoundError(f"Audio file not found: {audio_file_path}")


    # Blob expects base64-encoded bytes (the pydantic validator rejects a plain path string).
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
        youtube_url = _ensure_text(file)
        # Extract audio from YouTube and encode as base64
        audio_bytes = extract_audio_from_youtube(youtube_url)
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
            types.Part.from_text(text=AUDIO_PROMPT)
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
                                 
    generate_content_config = types.GenerateContentConfig(
        thinking_config = types.ThinkingConfig(
            thinking_budget=0,
        ),
        image_config=types.ImageConfig(
            image_size="1K",
        ),
        response_mime_type="application/json",
        response_schema = TranscriptResponse.model_json_schema(),
        system_instruction=prompt
    )

    subtopic_transcripts: List[SubtopicDialogue] = []
    accumulated_text = ""  # Accumulate all text chunks
    
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        # The streaming chunk may expose the generated text or structured response
        # in different attributes depending on SDK/version. First try parsing
        # the printed text as JSON (most reliable for structured outputs). If
        # that fails, fall back to attribute inspection.
        text = getattr(chunk, "text", None) or ""
        
        # Accumulate text for final parsing
        accumulated_text += text

        # Try JSON parse of the accumulated text (in case complete JSON is ready)
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict) and _extend_from_payload(parsed, subtopic_transcripts):
                break  # Successfully parsed, no need to continue
        except Exception:
            pass  # Not complete JSON yet, continue accumulating

        # Fallback: inspect attributes/model dump for structured data
        resp_data = None
        # older/newer SDKs may place data under chunk.response.data or inside
        # the model dump representation
        if hasattr(chunk, "response") and getattr(chunk, "response"):
            resp = getattr(chunk, "response")
            if hasattr(resp, "data") and getattr(resp, "data"):
                resp_data = getattr(resp, "data")

        if resp_data is None:
            # try pydantic model dump
            try:
                dumped = chunk.model_dump()
            except Exception:
                dumped = getattr(chunk, "__dict__", None)

            if isinstance(dumped, dict):
                # common places for the structured response
                if "response" in dumped and isinstance(dumped["response"], dict):
                    resp_data = dumped["response"].get("data")
                elif "data" in dumped and dumped["data"]:
                    resp_data = dumped["data"]
                elif "outputs" in dumped and dumped["outputs"]:
                    # sometimes outputs is a list of items containing 'content' or 'data'
                    for out in dumped["outputs"]:
                        if isinstance(out, dict) and "data" in out and out["data"]:
                            resp_data = out["data"]
                            break

        if resp_data and isinstance(resp_data, dict):
            if _extend_from_payload(resp_data, subtopic_transcripts):
                break
    
    # Final attempt: parse accumulated text if not already parsed
    if not subtopic_transcripts and accumulated_text:
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict):
                _extend_from_payload(parsed, subtopic_transcripts)
        except Exception:
            pass

    return subtopic_transcripts

def extract_quiz_transcripts(file, file_type):
    dotenv.load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    
    client = genai.Client(api_key=api_key)

    model = "gemini-2.5-flash"

    # Blob expects base64-encoded bytes (the pydantic validator rejects a plain path string).
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
            types.Part.from_text(text=AUDIO_QUIZ_PROMPT),
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
            types.Part.from_text(text=TEXT_QUIZ_PROMPT),
        ]
    elif file_type == "youtube":
        youtube_url = _ensure_text(file)
        # Extract audio from YouTube and encode as base64
        audio_bytes = extract_audio_from_youtube(youtube_url)
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
            types.Part.from_text(text=AUDIO_QUIZ_PROMPT)
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
            types.Part.from_text(text=PPTX_QUIZ_PROMPT)
        ]
                                 
    generate_content_config = types.GenerateContentConfig(
        thinking_config = types.ThinkingConfig(
            thinking_budget=0,
        ),
        image_config=types.ImageConfig(
            image_size="1K",
        ),
        response_mime_type="application/json",
        response_schema = QuizResponse.model_json_schema(),
        system_instruction=prompt
    )

    quiz_modules: List[QuizModule] = []
    accumulated_text = ""  # Accumulate all text chunks
    
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        text = getattr(chunk, "text", None) or ""
        
        # Accumulate text for final parsing
        accumulated_text += text

        # Try JSON parse of the accumulated text (in case complete JSON is ready)
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict) and _extend_from_quiz_payload(parsed, quiz_modules):
                break  # Successfully parsed, no need to continue
        except Exception:
            pass  # Not complete JSON yet, continue accumulating

        # Fallback: inspect attributes/model dump for structured data
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
            if _extend_from_quiz_payload(resp_data, quiz_modules):
                break
    
    # Final attempt: parse accumulated text if not already parsed
    if not quiz_modules and accumulated_text:
        try:
            parsed = json.loads(accumulated_text)
            if isinstance(parsed, dict):
                _extend_from_quiz_payload(parsed, quiz_modules)
        except Exception:
            pass

    return quiz_modules

if __name__ == "__main__":
    file = "C:\\Users\\Chris\\Downloads\\The essence of calculus.mp3"
    file_type = "audio/mp3"
    transcripts = extract_transcripts(file, file_type)
    for subtopic in transcripts:
        print(subtopic.model_dump())