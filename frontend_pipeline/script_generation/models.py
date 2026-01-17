"""Pydantic models describing transcript outputs."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ImageConfig(BaseModel):
    """Configuration for educational image overlay."""
    filename: str = Field(..., description="Image filename (e.g., 'diagram.png')")
    size: Literal["small", "medium", "large"] = Field(
        default="medium",
        description="Image size: 'small' (300px), 'medium' (540px), or 'large' (800px)"
    )
    position: Optional[str] = Field(
        default=None,
        description="Position on screen (e.g., 'top-right', 'top-left', 'top-center')"
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
    caption: str = Field(..., description="A sentence up to 30 words (auto-split if over 18 words).")
    speaker: Literal["PETER", "STEWIE"]
    emotion: Literal["neutral", "angry", "excited", "confused"]
    image: Optional[ImageConfig] = Field(
        default=None,
        description="Optional single educational image to display during this line"
    )
    images: Optional[List[ImageConfig]] = Field(
        default=None,
        description="Optional list of educational images to display simultaneously during this line"
    )
    duration_estimate: Optional[float] = Field(
        default=None,
        description="Estimated duration in seconds for this line of dialogue"
    )


class SingleDialogue(BaseModel):
    """A single conversational dialogue between Peter and Stewie."""
    title: str = Field(
        ...,
        description="A short title for this conversation.",
    )
    dialogue: List[DialogueLine]


class TranscriptResponse(BaseModel):
    """Response containing a single dialogue."""
    dialogue_data: SingleDialogue


# Deprecated: kept for backward compatibility with old code
class SubtopicDialogue(BaseModel):
    """DEPRECATED: Use SingleDialogue instead."""
    subtopic_title: str = Field(
        ...,
        description="A short title for the distinct subtopic.",
    )
    dialogue: List[DialogueLine]


__all__ = [
    "ImageConfig",
    "DialogueLine",
    "SingleDialogue",
    "TranscriptResponse",
    "SubtopicDialogue",  # Deprecated, kept for backward compatibility
]
