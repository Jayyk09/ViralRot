"""High-level audio service combining storage and database operations.

This module provides the main interface for audio operations, orchestrating
between storage backends and database repositories.
"""

from io import BytesIO
from uuid import uuid4
from typing import Optional

from backend_pipeline.audio_generation.minimax_tts import VOICE_MAP, generate_audio_from_dialouge
from storage import get_storage_backend


class AudioService:
    """High-level audio operations combining storage and TTS generation.

    This service combines storage operations (R2 or local) with audio generation
    to provide a clean, unified interface for creating and managing audio files.

    Usage:
        service = AudioService()

        # Generate and upload audio from dialogue
        result = service.create_and_upload_audio(
            dialogue="Hello, how are you today?",
            speaker="PETER"
        )
        print(result["presigned_url"])
        print(result["duration"])
    """

    def __init__(self, storage_backend: Optional[str] = None):
        """Initialize audio service.

        Args:
            storage_backend: Override storage backend ('r2' or 'local').
                If None, uses environment configuration.
        """
        if storage_backend:
            self.storage = get_storage_backend(backend_type=storage_backend, force_new=True)
        else:
            self.storage = get_storage_backend()

    def create_and_upload_audio(self, dialogue: str, speaker: str) -> dict:
        """Generate audio from dialogue text and upload to storage.

        Takes dialogue text and a speaker identifier, generates audio using
        text-to-speech, uploads the resulting audio file to the configured
        storage backend, and returns an access URL.

        Args:
            dialogue: The text to convert to speech.
            speaker: Speaker identifier (e.g., "PETER"). Falls back to "PETER"
                if the speaker is not found in VOICE_MAP.

        Returns:
            A dictionary containing:
                - presigned_url: URL to access the uploaded audio file.
                - duration: Duration of the generated audio in seconds.
        """
        voice_id = VOICE_MAP.get(speaker, VOICE_MAP["PETER"])
        audio_bytes, duration, _word_timestamps = generate_audio_from_dialouge(dialogue, voice_id)

        # Generate storage key
        audio_uuid = uuid4().hex
        storage_key = f"audio/segments/{audio_uuid}.mp3"

        # Upload to storage backend
        metadata = {"content_type": "audio/mpeg"}
        audio_buffer = BytesIO(audio_bytes)
        self.storage.upload(audio_buffer, storage_key, metadata)

        # Generate access URL
        access_url = self.storage.generate_url(storage_key)

        return {
            "presigned_url": access_url,
            "duration": duration,
        }
