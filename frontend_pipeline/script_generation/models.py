"""Pydantic models describing transcript outputs."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ImageConfig(BaseModel):
    """Configuration for educational image overlay."""
    filename: str = Field(..., description="Image filename (e.g., 'diagram.png')")
    size: Literal["medium", "large"] = Field(
        default="medium",
        description="Image size: 'medium' (top-right, 432px) or 'large' (top-center, 800px)"
    )
    start_time: Optional[float] = Field(
        default=None,
        description="Offset from line start in seconds (None = start immediately)"
    )
    duration: Optional[float] = Field(
        default=None,
        description="Display duration in seconds (None = entire line duration)"
    )


class DialogueLine(BaseModel):
    caption: str = Field(..., description="A single sentence under 20 words.")
    speaker: Literal["PETER", "STEWIE"]
    emotion: Literal["neutral", "angry", "excited", "confused"]
    image: Optional[ImageConfig] = Field(
        default=None,
        description="Optional educational image to display during this line"
    )


class SubtopicDialogue(BaseModel):
    subtopic_title: str = Field(
        ...,
        description="A short title for the distinct subtopic.",
    )
    dialogue: List[DialogueLine]


class TranscriptResponse(BaseModel):
    subtopic_transcripts: List[SubtopicDialogue]


__all__ = [
    "ImageConfig",
    "DialogueLine",
    "SubtopicDialogue",
    "TranscriptResponse",
]
