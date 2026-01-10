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


# Quiz models matching AUDIO_QUIZ_PROMPT, TEXT_QUIZ_PROMPT, YOUTUBE_QUIZ_PROMPT, PPTX_QUIZ_PROMPT


class QuizScript(BaseModel):
    """Scripts for asking and revealing quiz answers."""

    ask: str = Field(
        ...,
        description="Peter's spoken transcript asking the question. Must tell user to PAUSE. Under 25 words.",
    )
    reveal: str = Field(
        ...,
        description="Peter's spoken transcript revealing the answer with humor/education. Under 25 words.",
    )


class QuizQuestion(BaseModel):
    """A single quiz question with metadata and scripts."""

    question_number: int = Field(..., description="Sequential question number starting from 1.")
    type: Literal["multiple_choice", "fill_in_the_blank", "short_answer"] = Field(
        ...,
        description="Question type: primarily multiple_choice, with some fill_in_the_blank or short_answer.",
    )
    question_text: str = Field(..., description="The actual question text.")
    options: Optional[List[str]] = Field(
        None,
        description="List of answer options (for multiple_choice). Null for other types.",
    )
    correct_answer: str = Field(..., description="The correct answer.")
    script: QuizScript = Field(..., description="Peter's ask and reveal scripts.")


class QuizModule(BaseModel):
    """A quiz module for a specific subtopic with 3-6 questions."""

    subtopic_title: str = Field(
        ...,
        description="A short title for the academic subtopic (e.g., 'The Krebs Cycle').",
    )
    questions: List[QuizQuestion] = Field(
        ...,
        min_length=3,
        max_length=6,
        description="3 to 6 questions for this subtopic.",
    )


class QuizResponse(BaseModel):
    """Complete quiz response with modules for each subtopic."""

    quiz_modules: List[QuizModule] = Field(
        ...,
        description="List of quiz modules, one per academic subtopic.",
    )


__all__ = [
    "DialogueLine",
    "SubtopicDialogue",
    "TranscriptResponse",
    "QuizScript",
    "QuizQuestion",
    "QuizModule",
    "QuizResponse",
]