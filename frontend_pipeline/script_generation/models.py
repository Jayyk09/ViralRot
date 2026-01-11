"""Pydantic models describing transcript outputs."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class DialogueLine(BaseModel):
    caption: str = Field(..., description="A single sentence under 20 words.")
    speaker: Literal["PETER", "STEWIE"]
    emotion: Literal["neutral", "angry", "excited", "confused"]

class SubtopicDialogue(BaseModel):
    subtopic_title: str = Field(
        ...,
        description="A short title for the distinct subtopic.",
    )
    dialogue: List[DialogueLine]


class TranscriptResponse(BaseModel):
    subtopic_transcripts: List[SubtopicDialogue]


__all__ = [
    "DialogueLine",
    "SubtopicDialogue",
    "TranscriptResponse",
]
