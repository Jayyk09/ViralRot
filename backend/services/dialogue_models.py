"""Provider-independent dialogue models used by generation and persistence seams."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Speaker = str
Emotion = Literal["neutral", "angry", "excited", "confused"]
AudioEffectPlacement = Literal["before", "after", "under"]


class StrictDialogueModel(BaseModel):
    """Base model that rejects provider-added or legacy fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CharacterDefinition(StrictDialogueModel):
    """A generation character whose ID can later map to an image and voice."""

    id: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9_]+$")]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    persona: Annotated[str, Field(min_length=1, max_length=500)]


class AudioEffectCue(StrictDialogueModel):
    """A future audio-layer cue; generation records it but rendering is deferred."""

    description: Annotated[str, Field(min_length=1, max_length=80)]
    placement: AudioEffectPlacement


class DialogueLine(StrictDialogueModel):
    caption: Annotated[str, Field(min_length=1, max_length=240)]
    speaker: Annotated[Speaker, Field(min_length=1, max_length=40)]
    emotion: Emotion
    audio_effects: Annotated[list[AudioEffectCue], Field(max_length=2)] = Field(
        default_factory=list
    )

    @field_validator("caption", "speaker")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("dialogue text fields must not be blank")
        return value


class DialogueData(StrictDialogueModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    dialogue: Annotated[list[DialogueLine], Field(min_length=15, max_length=25)]

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class DialogueResponse(StrictDialogueModel):
    dialogue_data: DialogueData


__all__ = [
    "AudioEffectCue",
    "AudioEffectPlacement",
    "CharacterDefinition",
    "DialogueData",
    "DialogueLine",
    "DialogueResponse",
    "Emotion",
    "Speaker",
]
