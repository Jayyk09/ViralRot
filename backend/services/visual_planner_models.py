"""Provider-independent contracts for composition-bound visual planning."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonNegativeInt = Annotated[int, Field(ge=0)]
SearchQuery = Annotated[str, Field(min_length=1, max_length=160)]
StableId = Annotated[str, Field(min_length=1)]


class StrictVisualPlannerModel(BaseModel):
    """Base contract that rejects coercion and provider-added fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class PlannerNarrationLine(StrictVisualPlannerModel):
    """The only per-line data exposed to the visual-planning provider."""

    line_index: NonNegativeInt
    caption: Annotated[str, Field(min_length=1)]
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt

    @field_validator("caption")
    @classmethod
    def caption_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("caption must not be blank")
        return value

    @model_validator(mode="after")
    def timing_must_not_run_backwards(self) -> "PlannerNarrationLine":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class VisualPlannerInput(StrictVisualPlannerModel):
    """Complete ordered narration context sent to Grok."""

    title: Annotated[str, Field(min_length=1)]
    lines: Annotated[list[PlannerNarrationLine], Field(min_length=1)]

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value

    @model_validator(mode="after")
    def indexes_must_match_order(self) -> "VisualPlannerInput":
        indexes = [line.line_index for line in self.lines]
        expected = list(range(len(self.lines)))
        if indexes != expected:
            raise ValueError(
                "lines must be ordered with contiguous zero-based line_index values"
            )
        return self


class CapturedNarrationLine(StrictVisualPlannerModel):
    """One line from the captured active composition, including stable identity."""

    line_id: StableId
    line_index: NonNegativeInt
    caption: Annotated[str, Field(min_length=1)]
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt

    @field_validator("line_id", "caption")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def timing_must_not_run_backwards(self) -> "CapturedNarrationLine":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self

    def planner_line(self) -> PlannerNarrationLine:
        """Drop application identity before crossing the provider boundary."""

        return PlannerNarrationLine(
            line_index=self.line_index,
            caption=self.caption,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
        )


class CapturedNarrationSnapshot(StrictVisualPlannerModel):
    """Immutable-by-convention snapshot supplied by the active-composition caller."""

    composition_id: StableId
    title: Annotated[str, Field(min_length=1)]
    lines: Annotated[list[CapturedNarrationLine], Field(min_length=1)]

    @field_validator("composition_id", "title")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def lines_must_match_captured_order(self) -> "CapturedNarrationSnapshot":
        indexes = [line.line_index for line in self.lines]
        expected = list(range(len(self.lines)))
        if indexes != expected:
            raise ValueError(
                "lines must be ordered with contiguous zero-based line_index values"
            )
        line_ids = [line.line_id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("captured line_id values must be unique")
        return self

    def planner_input(self) -> VisualPlannerInput:
        """Build the redacted provider input from the complete snapshot."""

        return VisualPlannerInput(
            title=self.title,
            lines=[line.planner_line() for line in self.lines],
        )


class VisualPlanSlot(StrictVisualPlannerModel):
    """One provider-proposed inclusive line span and standalone image query."""

    start_line_index: NonNegativeInt
    end_line_index: NonNegativeInt
    search_query: SearchQuery

    @field_validator("search_query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("search_query must not be blank")
        return value


class VisualPlanResponse(StrictVisualPlannerModel):
    """Strict Grok output envelope; an empty plan is valid."""

    slots: Annotated[list[VisualPlanSlot], Field(max_length=12)]


class ResolvedVisualSlot(StrictVisualPlannerModel):
    """Transient slot resolved to stable line identities and [start, end) time."""

    start_line_id: StableId
    end_line_id: StableId
    start_ms: NonNegativeInt
    end_ms: NonNegativeInt
    search_query: SearchQuery

    @field_validator("start_line_id", "end_line_id", "search_query")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def timing_must_move_forward(self) -> "ResolvedVisualSlot":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class ResolvedVisualPlan(StrictVisualPlannerModel):
    """Composition-bound plan returned to later transient visual orchestration."""

    composition_id: StableId
    slots: Annotated[list[ResolvedVisualSlot], Field(max_length=12)]

    @field_validator("composition_id")
    @classmethod
    def composition_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("composition_id must not be blank")
        return value


__all__ = [
    "CapturedNarrationLine",
    "CapturedNarrationSnapshot",
    "PlannerNarrationLine",
    "ResolvedVisualPlan",
    "ResolvedVisualSlot",
    "StrictVisualPlannerModel",
    "VisualPlanResponse",
    "VisualPlanSlot",
    "VisualPlannerInput",
]
