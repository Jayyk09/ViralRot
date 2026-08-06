"""Incremental narration generation for persisted editor projects."""

import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Dict
from uuid import UUID, uuid4

from backend_pipeline.audio_generation.minimax_tts import (
    AUDIO_CONTENT_TYPE,
    AUDIO_EXTENSION,
    VOICE_MAP,
    concatenate_audio_segments,
    generate_audio_from_dialouge,
)
from services.repositories.editor_repository import EditorRepository
from storage import get_storage_backend


class EditorAudioService:
    def __init__(self) -> None:
        self.repository = EditorRepository()
        self.storage = get_storage_backend()

    def generate_narration(self, project_id: UUID, user_id: int) -> Dict[str, object]:
        project = self.repository.prepare_audio_generation(project_id, user_id)

        lines_to_generate = project["lines_to_generate"]
        for line_index, line in enumerate(lines_to_generate):
            voice_id = VOICE_MAP.get(line["speaker"], VOICE_MAP["PETER"])
            segment_id = uuid4()
            storage_key = (
                f"editor/{user_id}/{project_id}/segments/{segment_id}{AUDIO_EXTENSION}"
            )
            try:
                audio_bytes, duration, word_timings = generate_audio_from_dialouge(
                    line["caption"], voice_id
                )
                self.storage.upload(
                    BytesIO(audio_bytes),
                    storage_key,
                    {"content_type": AUDIO_CONTENT_TYPE},
                )
                self.repository.complete_audio_segment(
                    project_id=project_id,
                    line_id=line["id"],
                    user_id=user_id,
                    expected_revision=line["revision"],
                    segment_id=segment_id,
                    storage_key=storage_key,
                    duration_ms=max(0, round(duration * 1000)),
                    voice_id=voice_id,
                    word_timings=word_timings,
                )
            except Exception as exc:
                self.storage.delete(storage_key)
                self.repository.fail_audio_segment(
                    project_id, line["id"], user_id, str(exc)
                )
                for pending in lines_to_generate[line_index + 1:]:
                    self.repository.fail_audio_segment(
                        project_id,
                        pending["id"],
                        user_id,
                        "Narration generation was cancelled after another line failed",
                    )
                raise

        inputs = self.repository.get_composition_inputs(project_id, user_id)
        temp_dir = Path(tempfile.mkdtemp(prefix="editor-composition-"))
        try:
            segment_records = []
            for index, row in enumerate(inputs):
                local_path = temp_dir / f"segment_{index:04d}{AUDIO_EXTENSION}"
                self.storage.download(row["storage_key"], str(local_path))
                segment_records.append(
                    {
                        "index": index,
                        "line_id": str(row["line_id"]),
                        "file": str(local_path),
                        "caption": row["caption"],
                        "speaker": row["speaker"],
                        "emotion": row["emotion"] or "neutral",
                        "duration": row["duration_ms"] / 1000,
                        "word_timestamps": row["word_timings"] or [],
                    }
                )

            output_path = temp_dir / f"composition{AUDIO_EXTENSION}"
            composed = concatenate_audio_segments(segment_records, str(output_path))
            composition_id = uuid4()
            composition_key = (
                f"editor/{user_id}/{project_id}/compositions/{composition_id}{AUDIO_EXTENSION}"
            )
            with output_path.open("rb") as audio_file:
                self.storage.upload(
                    audio_file,
                    composition_key,
                    {"content_type": AUDIO_CONTENT_TYPE},
                )

            manifest = [
                {
                    "line_id": timing["line_id"],
                    "segment_id": str(inputs[index]["segment_id"]),
                    "start_ms": round(timing["start"] * 1000),
                    "end_ms": round(timing["end"] * 1000),
                    "caption": timing["caption"],
                    "speaker": timing["speaker"],
                    "emotion": timing["emotion"],
                }
                for index, timing in enumerate(composed["timings"])
            ]
            duration_ms = round(composed["total_duration"] * 1000)
            try:
                self.repository.activate_composition(
                    project_id,
                    user_id,
                    composition_id,
                    composition_key,
                    duration_ms,
                    manifest,
                )
            except Exception:
                self.storage.delete(composition_key)
                raise
            return {
                "composition_id": str(composition_id),
                "storage_key": composition_key,
                "duration_ms": duration_ms,
                "line_manifest": manifest,
                "word_timestamps": composed["word_timestamps"],
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
