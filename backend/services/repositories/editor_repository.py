"""Persistence operations for editor projects and dialogue lines."""

import json
from typing import Dict, List, NotRequired, Optional, TypedDict
from uuid import UUID, uuid4

from psycopg2.extras import RealDictCursor

from db import get_db_conn


class EditorLineInput(TypedDict):
    """Validated dialogue fields accepted by the persistence layer."""

    caption: str
    speaker: str
    emotion: NotRequired[Optional[str]]


class EditorProjectNotFoundError(Exception):
    """Raised when a project or line is not owned by the current user."""


class EditorRevisionConflictError(Exception):
    """Raised when an editor write is based on a stale revision."""


class EditorLineGeneratingError(Exception):
    """Raised when a line is edited while its audio is being generated."""


class EditorInvalidOrderError(Exception):
    """Raised when a reorder request does not contain every project line once."""


class EditorCompositionRequiredError(Exception):
    """Raised when a visual edit is attempted without an active narration."""


class EditorClipValidationError(Exception):
    """Raised when clip timing or geometry is invalid for the timeline."""


class MediaAssetLimitError(Exception):
    """Raised when a project has reached its media asset quota."""


class MediaAssetInUseError(Exception):
    """Raised when deleting a media asset that timeline clips still reference."""

    def __init__(self, referencing_clip_ids: List[UUID]):
        self.referencing_clip_ids = [str(clip_id) for clip_id in referencing_clip_ids]
        super().__init__(
            f"Media asset is referenced by {len(referencing_clip_ids)} timeline clip(s)"
        )


# Geometry tolerance: the editor clamps interactively, so only float rounding
# should ever push x + width past 1.
_GEOMETRY_EPSILON = 0.001


def clamp_clip_window(start_ms: int, end_ms: int, duration_ms: int) -> tuple:
    """Clamp a clip window to the composition duration.

    The start must fall inside the narration; the end is clamped to the
    composition duration. Returns the (start_ms, end_ms) to persist.
    """
    if start_ms < 0:
        raise EditorClipValidationError("start_ms must be at least 0")
    if start_ms >= duration_ms:
        raise EditorClipValidationError(
            f"start_ms {start_ms} is beyond the narration duration {duration_ms}"
        )
    clamped_end = min(end_ms, duration_ms)
    if clamped_end <= start_ms:
        raise EditorClipValidationError("end_ms must be greater than start_ms")
    if clamped_end - start_ms < 500:
        raise EditorClipValidationError("Visual clips must be at least 0.5 seconds long")
    return start_ms, clamped_end


def validate_clip_geometry(
    x: float,
    y: float,
    width: float,
    asset_width_px: Optional[int] = None,
    asset_height_px: Optional[int] = None,
) -> None:
    """Server-side re-check of normalized clip geometry (API is the trust boundary).

    The output is fixed at 1080x1920. When intrinsic asset dimensions are
    known, derive the normalized height and require the full image to remain
    inside the frame, matching the canvas editor's aspect-preserving clamp.
    """
    if not (0 <= x <= 1):
        raise EditorClipValidationError("x must be between 0 and 1")
    if not (0 <= y <= 1):
        raise EditorClipValidationError("y must be between 0 and 1")
    if not (0 < width <= 1):
        raise EditorClipValidationError("width must be greater than 0 and at most 1")
    if x + width > 1 + _GEOMETRY_EPSILON:
        raise EditorClipValidationError("Clip must fit horizontally within the frame")
    if asset_width_px and asset_height_px:
        normalized_height = width * (asset_height_px / asset_width_px) * (1080 / 1920)
        if y + normalized_height > 1 + _GEOMETRY_EPSILON:
            raise EditorClipValidationError("Clip must fit vertically within the frame")


def validate_z_index(z_index: int) -> None:
    if z_index < -1000 or z_index > 1000:
        raise EditorClipValidationError("z_index must be between -1000 and 1000")


class EditorRepository:
    """Store and retrieve editor projects using short, explicit transactions."""

    def create_project(
        self,
        user_id: int,
        title: str,
        background_video_id: Optional[str],
        dialogue: List[EditorLineInput],
    ) -> Dict[str, object]:
        project_id = uuid4()
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO editor_projects (id, user_id, title, background_video_id)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (project_id, user_id, title, background_video_id),
                    )
                    for position, line in enumerate(dialogue):
                        cur.execute(
                            """
                            INSERT INTO dialogue_lines
                                (id, project_id, position, caption, speaker, emotion)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                uuid4(),
                                project_id,
                                position,
                                line["caption"],
                                line["speaker"],
                                line.get("emotion"),
                            ),
                        )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def get_project(self, project_id: UUID, user_id: int) -> Optional[Dict[str, object]]:
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                return self._get_project(cur, project_id, user_id, required=False)
        finally:
            conn.close()

    def update_project(
        self,
        project_id: UUID,
        user_id: int,
        title: str,
        background_video_id: Optional[str],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        UPDATE editor_projects
                        SET title = %s,
                            background_video_id = %s,
                            revision = revision + 1,
                            updated_at = NOW()
                        WHERE id = %s AND user_id = %s AND revision = %s
                        RETURNING id
                        """,
                        (title, background_video_id, project_id, user_id, expected_revision),
                    )
                    if cur.fetchone() is None:
                        self._raise_project_update_error(
                            cur, project_id, user_id, expected_revision
                        )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def update_line(
        self,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        caption: str,
        speaker: str,
        emotion: Optional[str],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        UPDATE dialogue_lines AS line
                        SET caption = %s,
                            speaker = %s,
                            emotion = %s,
                            revision = line.revision + 1,
                            audio_status = 'stale',
                            audio_error = NULL,
                            active_segment_id = NULL,
                            updated_at = NOW()
                        FROM editor_projects AS project
                        WHERE line.id = %s
                          AND line.project_id = %s
                          AND project.id = line.project_id
                          AND project.user_id = %s
                          AND line.revision = %s
                          AND line.audio_status <> 'generating'
                        RETURNING line.id, line.position, line.caption, line.speaker,
                                  line.emotion, line.revision, line.audio_status,
                                  line.audio_error, line.active_segment_id,
                                  line.created_at, line.updated_at
                        """,
                        (
                            caption,
                            speaker,
                            emotion,
                            line_id,
                            project_id,
                            user_id,
                            expected_revision,
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        self._raise_line_update_error(
                            cur, project_id, line_id, user_id, expected_revision
                        )

                    self._invalidate_composition(cur, project_id, user_id)
                    return dict(row)
        finally:
            conn.close()

    def restore_narrated_script(
        self,
        project_id: UUID,
        user_id: int,
        expected_project_revision: int,
    ) -> Dict[str, object]:
        """Restore dialogue fields from the most recent generated composition.

        This intentionally supports non-structural edits only. Media assets and
        timeline clips are not touched; restoring the exact old composition also
        restores the timeline duration those clips were authored against.
        """
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_project_revision)
                    cur.execute(
                        """
                        SELECT id, line_manifest
                        FROM audio_compositions
                        WHERE project_id = %s
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        FOR UPDATE
                        """,
                        (project_id,),
                    )
                    composition = cur.fetchone()
                    if composition is None:
                        raise EditorCompositionRequiredError(
                            "This project has no narrated script to restore"
                        )

                    manifest = composition["line_manifest"] or []
                    cur.execute(
                        "SELECT id FROM dialogue_lines WHERE project_id = %s ORDER BY position FOR UPDATE",
                        (project_id,),
                    )
                    current_ids = [str(row["id"]) for row in cur.fetchall()]
                    manifest_ids = [str(entry["line_id"]) for entry in manifest]
                    if current_ids != manifest_ids:
                        raise EditorInvalidOrderError(
                            "The narrated script cannot be restored after adding, deleting, or reordering lines"
                        )

                    for entry in manifest:
                        cur.execute(
                            """
                            UPDATE dialogue_lines
                            SET caption = %s, speaker = %s, emotion = %s,
                                active_segment_id = %s, audio_status = 'ready',
                                audio_error = NULL, revision = revision + 1,
                                updated_at = NOW()
                            WHERE id = %s AND project_id = %s
                            """,
                            (
                                entry.get("caption", ""),
                                entry.get("speaker", "PETER"),
                                entry.get("emotion") or "neutral",
                                entry["segment_id"],
                                entry["line_id"],
                                project_id,
                            ),
                        )
                        if cur.rowcount != 1:
                            raise EditorRevisionConflictError(
                                "Dialogue changed while restoring narration"
                            )

                    cur.execute(
                        """
                        UPDATE editor_projects
                        SET active_composition_id = %s, revision = revision + 1,
                            updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (composition["id"], project_id, user_id),
                    )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def add_line(
        self,
        project_id: UUID,
        user_id: int,
        line: EditorLineInput,
        position: Optional[int],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_revision)
                    cur.execute(
                        "SELECT COUNT(*) AS count FROM dialogue_lines WHERE project_id = %s",
                        (project_id,),
                    )
                    count = int(cur.fetchone()["count"])
                    insert_at = count if position is None else position
                    if insert_at < 0 or insert_at > count:
                        raise EditorInvalidOrderError(
                            f"Position must be between 0 and {count}"
                        )

                    cur.execute("SET CONSTRAINTS uq_dialogue_lines_project_position DEFERRED")
                    cur.execute(
                        """
                        UPDATE dialogue_lines
                        SET position = position + 1, updated_at = NOW()
                        WHERE project_id = %s AND position >= %s
                        """,
                        (project_id, insert_at),
                    )
                    cur.execute(
                        """
                        INSERT INTO dialogue_lines
                            (id, project_id, position, caption, speaker, emotion)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uuid4(),
                            project_id,
                            insert_at,
                            line["caption"],
                            line["speaker"],
                            line.get("emotion"),
                        ),
                    )
                    self._advance_project_revision(cur, project_id, user_id)
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def delete_line(
        self,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_revision)
                    cur.execute(
                        """
                        DELETE FROM dialogue_lines
                        WHERE id = %s AND project_id = %s
                        RETURNING position
                        """,
                        (line_id, project_id),
                    )
                    deleted = cur.fetchone()
                    if deleted is None:
                        raise EditorProjectNotFoundError("Dialogue line not found")

                    cur.execute("SET CONSTRAINTS uq_dialogue_lines_project_position DEFERRED")
                    cur.execute(
                        """
                        UPDATE dialogue_lines
                        SET position = position - 1, updated_at = NOW()
                        WHERE project_id = %s AND position > %s
                        """,
                        (project_id, deleted["position"]),
                    )
                    self._advance_project_revision(cur, project_id, user_id)
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def reorder_lines(
        self,
        project_id: UUID,
        user_id: int,
        line_ids: List[UUID],
        expected_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_revision)
                    cur.execute(
                        "SELECT id FROM dialogue_lines WHERE project_id = %s ORDER BY position FOR UPDATE",
                        (project_id,),
                    )
                    current_ids = [row["id"] for row in cur.fetchall()]
                    if len(line_ids) != len(set(line_ids)) or set(line_ids) != set(current_ids):
                        raise EditorInvalidOrderError(
                            "line_ids must contain every project dialogue line exactly once"
                        )

                    cur.execute("SET CONSTRAINTS uq_dialogue_lines_project_position DEFERRED")
                    for position, line_id in enumerate(line_ids):
                        cur.execute(
                            """
                            UPDATE dialogue_lines
                            SET position = %s, updated_at = NOW()
                            WHERE id = %s AND project_id = %s
                            """,
                            (position, line_id, project_id),
                        )
                    self._advance_project_revision(cur, project_id, user_id)
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Media assets & timeline clips (visual layer)
    #
    # Visual mutations must never invalidate active_composition_id: they use
    # _advance_project_revision_keep_composition, never
    # _advance_project_revision (which nulls the composition and would force
    # narration regeneration for a purely visual edit).
    # ------------------------------------------------------------------

    def create_media_asset(
        self,
        project_id: UUID,
        user_id: int,
        asset_id: UUID,
        storage_key: str,
        original_filename: str,
        content_type: str,
        byte_size: int,
        width_px: int,
        height_px: int,
    ) -> Dict[str, object]:
        """Persist an already-normalized, already-uploaded image asset.

        Callers upload the bytes first and compensate (delete the object) if
        this insert fails, so every persisted row is immediately 'ready'.
        """
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT id FROM editor_projects WHERE id = %s AND user_id = %s FOR UPDATE",
                        (project_id, user_id),
                    )
                    if cur.fetchone() is None:
                        raise EditorProjectNotFoundError("Editor project not found")
                    cur.execute(
                        "SELECT COUNT(*) AS count FROM media_assets WHERE project_id = %s",
                        (project_id,),
                    )
                    if cur.fetchone()["count"] >= 20:
                        raise MediaAssetLimitError(
                            "A project can contain at most 20 uploaded images"
                        )
                    cur.execute(
                        """
                        INSERT INTO media_assets
                            (id, user_id, project_id, storage_key, original_filename,
                             content_type, byte_size, width_px, height_px)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, project_id, storage_key, original_filename,
                                  content_type, byte_size, width_px, height_px,
                                  status, created_at
                        """,
                        (
                            asset_id,
                            user_id,
                            project_id,
                            storage_key,
                            original_filename,
                            content_type,
                            byte_size,
                            width_px,
                            height_px,
                        ),
                    )
                    return dict(cur.fetchone())
        finally:
            conn.close()

    def get_media_asset(
        self, project_id: UUID, asset_id: UUID, user_id: int
    ) -> Dict[str, object]:
        """Load one owned media asset (used by the dev content passthrough)."""
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT asset.id, asset.project_id, asset.storage_key,
                           asset.original_filename, asset.content_type,
                           asset.byte_size, asset.width_px, asset.height_px,
                           asset.status, asset.created_at
                    FROM media_assets AS asset
                    JOIN editor_projects AS project ON project.id = asset.project_id
                    WHERE asset.id = %s AND asset.project_id = %s AND project.user_id = %s
                    """,
                    (asset_id, project_id, user_id),
                )
                asset = cur.fetchone()
                if asset is None:
                    raise EditorProjectNotFoundError("Media asset not found")
                return dict(asset)
        finally:
            conn.close()

    def delete_media_asset(
        self, project_id: UUID, asset_id: UUID, user_id: int
    ) -> str:
        """Delete an owned, unreferenced asset row and return its storage key.

        Raises MediaAssetInUseError (with the referencing clip ids) when any
        timeline clip still uses the asset.
        """
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT asset.id, asset.storage_key
                        FROM media_assets AS asset
                        JOIN editor_projects AS project ON project.id = asset.project_id
                        WHERE asset.id = %s AND asset.project_id = %s AND project.user_id = %s
                        FOR UPDATE OF asset
                        """,
                        (asset_id, project_id, user_id),
                    )
                    asset = cur.fetchone()
                    if asset is None:
                        raise EditorProjectNotFoundError("Media asset not found")
                    cur.execute(
                        "SELECT id FROM timeline_clips WHERE asset_id = %s ORDER BY created_at",
                        (asset_id,),
                    )
                    clip_ids = [row["id"] for row in cur.fetchall()]
                    if clip_ids:
                        raise MediaAssetInUseError(clip_ids)
                    cur.execute("DELETE FROM media_assets WHERE id = %s", (asset_id,))
                    return asset["storage_key"]
        finally:
            conn.close()

    def create_timeline_clip(
        self,
        project_id: UUID,
        user_id: int,
        asset_id: UUID,
        start_ms: int,
        end_ms: int,
        x: float,
        y: float,
        width: float,
        z_index: int,
        expected_project_revision: int,
    ) -> Dict[str, object]:
        """Place an asset on the timeline; requires an active narration."""
        validate_z_index(z_index)
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_project_revision)
                    composition = self._require_active_composition(cur, project_id)
                    cur.execute(
                        "SELECT id, width_px, height_px FROM media_assets WHERE id = %s AND project_id = %s",
                        (asset_id, project_id),
                    )
                    asset = cur.fetchone()
                    if asset is None:
                        raise EditorProjectNotFoundError("Media asset not found")
                    validate_clip_geometry(
                        x, y, width, asset["width_px"], asset["height_px"]
                    )
                    start, end = clamp_clip_window(
                        start_ms, end_ms, composition["duration_ms"]
                    )
                    cur.execute(
                        """
                        INSERT INTO timeline_clips
                            (id, project_id, asset_id, start_ms, end_ms, x, y, width,
                             z_index, authored_composition_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            uuid4(),
                            project_id,
                            asset_id,
                            start,
                            end,
                            x,
                            y,
                            width,
                            z_index,
                            composition["id"],
                        ),
                    )
                    self._advance_project_revision_keep_composition(
                        cur, project_id, user_id
                    )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def update_timeline_clip(
        self,
        project_id: UUID,
        clip_id: UUID,
        user_id: int,
        updates: Dict[str, object],
        expected_revision: int,
    ) -> Dict[str, object]:
        """Autosave-style clip edit: clip-scoped revision, project untouched.

        Swapping asset_id preserves geometry/timing (only provided fields
        change). Retiming re-authors the clip against the active composition
        and clamps to its duration; geometry-only edits leave timing fields
        and timing_status untouched.
        """
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Serialize against composition activation so a retime can
                    # never clamp against an old duration after reconciliation.
                    cur.execute(
                        "SELECT id FROM editor_projects WHERE id = %s AND user_id = %s FOR SHARE",
                        (project_id, user_id),
                    )
                    if cur.fetchone() is None:
                        raise EditorProjectNotFoundError("Editor project not found")
                    cur.execute(
                        """
                        SELECT clip.id, clip.asset_id, clip.start_ms, clip.end_ms,
                               clip.x, clip.y, clip.width, clip.z_index,
                               clip.timing_status, clip.authored_composition_id,
                               clip.revision,
                               asset.width_px AS asset_width_px,
                               asset.height_px AS asset_height_px,
                               composition.id AS composition_id,
                               composition.duration_ms AS composition_duration_ms
                        FROM timeline_clips AS clip
                        JOIN editor_projects AS project ON project.id = clip.project_id
                        JOIN media_assets AS asset ON asset.id = clip.asset_id
                        LEFT JOIN audio_compositions AS composition
                          ON composition.id = project.active_composition_id
                        WHERE clip.id = %s AND clip.project_id = %s AND project.user_id = %s
                        FOR UPDATE OF clip
                        """,
                        (clip_id, project_id, user_id),
                    )
                    current = cur.fetchone()
                    if current is None:
                        raise EditorProjectNotFoundError("Timeline clip not found")
                    if current["revision"] != expected_revision:
                        raise EditorRevisionConflictError(
                            f"Expected clip revision {expected_revision}, "
                            f"but current revision is {current['revision']}"
                        )
                    if current["composition_id"] is None:
                        raise EditorCompositionRequiredError(
                            "Regenerate narration before editing visuals"
                        )

                    asset_width_px = current["asset_width_px"]
                    asset_height_px = current["asset_height_px"]
                    if "asset_id" in updates:
                        cur.execute(
                            "SELECT id, width_px, height_px FROM media_assets WHERE id = %s AND project_id = %s",
                            (updates["asset_id"], project_id),
                        )
                        replacement_asset = cur.fetchone()
                        if replacement_asset is None:
                            raise EditorProjectNotFoundError("Media asset not found")
                        asset_width_px = replacement_asset["width_px"]
                        asset_height_px = replacement_asset["height_px"]

                    x = updates.get("x", current["x"])
                    y = updates.get("y", current["y"])
                    width = updates.get("width", current["width"])
                    validate_clip_geometry(
                        float(x), float(y), float(width), asset_width_px, asset_height_px
                    )

                    if "z_index" in updates:
                        validate_z_index(int(updates["z_index"]))

                    retimed = "start_ms" in updates or "end_ms" in updates
                    start = updates.get("start_ms", current["start_ms"])
                    end = updates.get("end_ms", current["end_ms"])
                    if retimed:
                        start, end = clamp_clip_window(
                            start, end, current["composition_duration_ms"]
                        )
                        timing_status = "aligned"
                        authored_composition_id = current["composition_id"]
                    else:
                        timing_status = current["timing_status"]
                        authored_composition_id = current["authored_composition_id"]

                    cur.execute(
                        """
                        UPDATE timeline_clips
                        SET asset_id = %s, start_ms = %s, end_ms = %s,
                            x = %s, y = %s, width = %s, z_index = %s,
                            authored_composition_id = %s, timing_status = %s,
                            revision = revision + 1, updated_at = NOW()
                        WHERE id = %s AND revision = %s
                        RETURNING id, project_id, asset_id, start_ms, end_ms, x, y,
                                  width, z_index, authored_composition_id,
                                  timing_status, revision, created_at, updated_at
                        """,
                        (
                            updates.get("asset_id", current["asset_id"]),
                            start,
                            end,
                            x,
                            y,
                            width,
                            updates.get("z_index", current["z_index"]),
                            authored_composition_id,
                            timing_status,
                            clip_id,
                            expected_revision,
                        ),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise EditorRevisionConflictError(
                            "Timeline clip changed while saving"
                        )
                    return dict(row)
        finally:
            conn.close()

    def delete_timeline_clip(
        self,
        project_id: UUID,
        clip_id: UUID,
        user_id: int,
        expected_project_revision: int,
    ) -> Dict[str, object]:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    self._lock_project(cur, project_id, user_id, expected_project_revision)
                    cur.execute(
                        "DELETE FROM timeline_clips WHERE id = %s AND project_id = %s RETURNING id",
                        (clip_id, project_id),
                    )
                    if cur.fetchone() is None:
                        raise EditorProjectNotFoundError("Timeline clip not found")
                    self._advance_project_revision_keep_composition(
                        cur, project_id, user_id
                    )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

    def _require_active_composition(
        self, cur: RealDictCursor, project_id: UUID
    ) -> Dict[str, object]:
        """Visual editing requires an active narration timeline to clamp against."""
        cur.execute(
            """
            SELECT composition.id, composition.duration_ms
            FROM editor_projects AS project
            JOIN audio_compositions AS composition
              ON composition.id = project.active_composition_id
            WHERE project.id = %s
            """,
            (project_id,),
        )
        composition = cur.fetchone()
        if composition is None:
            raise EditorCompositionRequiredError(
                "Regenerate narration before editing visuals"
            )
        return composition

    def _advance_project_revision_keep_composition(
        self, cur: RealDictCursor, project_id: UUID, user_id: int
    ) -> None:
        """Bump the project revision WITHOUT invalidating the narration."""
        cur.execute(
            """
            UPDATE editor_projects
            SET revision = revision + 1,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (project_id, user_id),
        )

    def _get_project(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        user_id: int,
        required: bool = True,
    ) -> Optional[Dict[str, object]]:
        """Load one owned project and its ordered dialogue in the same connection."""
        cur.execute(
            """
            SELECT project.id, project.user_id, project.title,
                   project.background_video_id, project.revision,
                   project.active_composition_id,
                   composition.storage_key AS active_composition_storage_key,
                   composition.duration_ms AS active_composition_duration_ms,
                   composition.line_manifest AS active_composition_line_manifest,
                   project.created_at, project.updated_at
            FROM editor_projects AS project
            LEFT JOIN audio_compositions AS composition
              ON composition.id = project.active_composition_id
            WHERE project.id = %s AND project.user_id = %s
            """,
            (project_id, user_id),
        )
        project = cur.fetchone()
        if project is None:
            if required:
                raise EditorProjectNotFoundError("Editor project not found")
            return None

        cur.execute(
            """
            SELECT line.id, line.position, line.caption, line.speaker,
                   line.emotion, line.revision, line.audio_status,
                   line.audio_error, line.active_segment_id,
                   line.created_at, line.updated_at,
                   segment.storage_key AS active_segment_storage_key,
                   segment.duration_ms AS active_segment_duration_ms,
                   segment.word_timings AS active_segment_word_timings
            FROM dialogue_lines AS line
            LEFT JOIN audio_segments AS segment
              ON segment.id = line.active_segment_id
            WHERE line.project_id = %s
            ORDER BY line.position
            """,
            (project_id,),
        )
        result = dict(project)
        result["dialogue"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, s3_key AS storage_key, video_title AS title, created_at
            FROM videos
            WHERE editor_project_id = %s AND user_id = %s
            ORDER BY created_at DESC
            """,
            (project_id, user_id),
        )
        result["exports"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, project_id, storage_key, original_filename, content_type,
                   byte_size, width_px, height_px, status, created_at
            FROM media_assets
            WHERE project_id = %s AND user_id = %s
            ORDER BY created_at, id
            """,
            (project_id, user_id),
        )
        result["media_assets"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, project_id, asset_id, start_ms, end_ms, x, y, width,
                   z_index, authored_composition_id, timing_status, revision,
                   created_at, updated_at
            FROM timeline_clips
            WHERE project_id = %s
            ORDER BY z_index, created_at, id
            """,
            (project_id,),
        )
        result["timeline_clips"] = [dict(row) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT line_manifest
            FROM audio_compositions
            WHERE project_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        )
        checkpoint = cur.fetchone()
        current_line_ids = [str(line["id"]) for line in result["dialogue"]]
        checkpoint_line_ids = (
            [str(entry["line_id"]) for entry in checkpoint["line_manifest"]]
            if checkpoint else []
        )
        result["can_restore_narrated_script"] = bool(
            checkpoint and current_line_ids == checkpoint_line_ids
        )
        return result

    def prepare_audio_generation(
        self, project_id: UUID, user_id: int
    ) -> Dict[str, object]:
        """Claim every missing/stale/failed line and return the project snapshot."""
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    project = self._get_project(cur, project_id, user_id)
                    lines = project["dialogue"]
                    if not lines:
                        raise EditorInvalidOrderError("Project has no dialogue lines")
                    if any(line["audio_status"] == "generating" for line in lines):
                        raise EditorLineGeneratingError("Narration generation is already running")
                    line_ids = [
                        line["id"]
                        for line in lines
                        if line["audio_status"] in {"missing", "stale", "failed"}
                        or not line["active_segment_id"]
                    ]
                    if line_ids:
                        cur.execute(
                            """
                            UPDATE dialogue_lines
                            SET audio_status = 'generating', audio_error = NULL, updated_at = NOW()
                            WHERE project_id = %s AND id = ANY(%s)
                            """,
                            (project_id, line_ids),
                        )
                    project["lines_to_generate"] = [
                        line for line in lines if line["id"] in set(line_ids)
                    ]
                    return project
        finally:
            conn.close()

    def complete_audio_segment(
        self,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
        segment_id: UUID,
        storage_key: str,
        duration_ms: int,
        voice_id: str,
        word_timings: List[Dict[str, object]],
    ) -> None:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO audio_segments
                            (id, line_id, storage_key, duration_ms, voice_id, word_timings)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (segment_id, line_id, storage_key, duration_ms, voice_id, json.dumps(word_timings)),
                    )
                    cur.execute(
                        """
                        UPDATE dialogue_lines AS line
                        SET active_segment_id = %s, audio_status = 'ready',
                            audio_error = NULL, updated_at = NOW()
                        FROM editor_projects AS project
                        WHERE line.id = %s AND line.project_id = %s
                          AND project.id = line.project_id AND project.user_id = %s
                          AND line.revision = %s AND line.audio_status = 'generating'
                        """,
                        (segment_id, line_id, project_id, user_id, expected_revision),
                    )
                    if cur.rowcount != 1:
                        raise EditorRevisionConflictError(
                            "Dialogue changed while narration was generating"
                        )
        finally:
            conn.close()

    def fail_audio_segment(
        self, project_id: UUID, line_id: UUID, user_id: int, error: str
    ) -> None:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE dialogue_lines AS line
                        SET audio_status = 'failed', audio_error = %s, updated_at = NOW()
                        FROM editor_projects AS project
                        WHERE line.id = %s AND line.project_id = %s
                          AND project.id = line.project_id AND project.user_id = %s
                        """,
                        (error[:2000], line_id, project_id, user_id),
                    )
        finally:
            conn.close()

    def get_composition_inputs(
        self, project_id: UUID, user_id: int
    ) -> List[Dict[str, object]]:
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT line.id AS line_id, line.position, line.caption,
                           line.speaker, line.emotion, line.audio_status,
                           segment.id AS segment_id, segment.storage_key,
                           segment.duration_ms, segment.word_timings
                    FROM dialogue_lines AS line
                    JOIN editor_projects AS project ON project.id = line.project_id
                    LEFT JOIN audio_segments AS segment ON segment.id = line.active_segment_id
                    WHERE line.project_id = %s AND project.user_id = %s
                    ORDER BY line.position
                    """,
                    (project_id, user_id),
                )
                rows = [dict(row) for row in cur.fetchall()]
                if not rows or any(
                    row["audio_status"] != "ready" or not row["segment_id"]
                    for row in rows
                ):
                    raise EditorRevisionConflictError(
                        "Every dialogue line needs ready narration"
                    )
                return rows
        finally:
            conn.close()

    def activate_composition(
        self,
        project_id: UUID,
        user_id: int,
        composition_id: UUID,
        storage_key: str,
        duration_ms: int,
        line_manifest: List[Dict[str, object]],
    ) -> None:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO audio_compositions
                            (id, project_id, storage_key, duration_ms, line_manifest)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        """,
                        (composition_id, project_id, storage_key, duration_ms, json.dumps(line_manifest)),
                    )
                    cur.execute(
                        """
                        UPDATE editor_projects
                        SET active_composition_id = %s, updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (composition_id, project_id, user_id),
                    )
                    if cur.rowcount != 1:
                        raise EditorProjectNotFoundError("Editor project not found")
                    self._reconcile_clips_with_composition(
                        cur, project_id, composition_id, duration_ms
                    )
        finally:
            conn.close()

    def _reconcile_clips_with_composition(
        self,
        cur,
        project_id: UUID,
        composition_id: UUID,
        duration_ms: int,
    ) -> None:
        """Fit existing clips to a newly activated narration timeline.

        Clips that still start inside the new narration keep their absolute
        times, get their ends clamped to the new duration, and are re-authored
        against the new composition. Clips that start beyond the new duration
        are kept (never deleted) but flagged 'needs_review' so the UI can
        surface them; they keep their old authored_composition_id.
        """
        cur.execute(
            """
            UPDATE timeline_clips
            SET end_ms = LEAST(end_ms, %s),
                authored_composition_id = %s,
                timing_status = 'aligned',
                revision = revision + 1,
                updated_at = NOW()
            WHERE project_id = %s AND start_ms <= %s
            """,
            (duration_ms, composition_id, project_id, duration_ms - 500),
        )
        cur.execute(
            """
            UPDATE timeline_clips
            SET timing_status = 'needs_review',
                revision = revision + 1,
                updated_at = NOW()
            WHERE project_id = %s AND start_ms > %s
            """,
            (project_id, duration_ms - 500),
        )

    def _lock_project(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        cur.execute(
            "SELECT revision FROM editor_projects WHERE id = %s AND user_id = %s FOR UPDATE",
            (project_id, user_id),
        )
        project = cur.fetchone()
        if project is None:
            raise EditorProjectNotFoundError("Editor project not found")
        if project["revision"] != expected_revision:
            raise EditorRevisionConflictError(
                f"Expected project revision {expected_revision}, but current revision is {project['revision']}"
            )

    def _advance_project_revision(
        self, cur: RealDictCursor, project_id: UUID, user_id: int
    ) -> None:
        cur.execute(
            """
            UPDATE editor_projects
            SET revision = revision + 1,
                active_composition_id = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (project_id, user_id),
        )

    def _invalidate_composition(
        self, cur: RealDictCursor, project_id: UUID, user_id: int
    ) -> None:
        cur.execute(
            """
            UPDATE editor_projects
            SET active_composition_id = NULL, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (project_id, user_id),
        )

    def _raise_project_update_error(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        cur.execute(
            "SELECT revision FROM editor_projects WHERE id = %s AND user_id = %s",
            (project_id, user_id),
        )
        current = cur.fetchone()
        if current is None:
            raise EditorProjectNotFoundError("Editor project not found")
        raise EditorRevisionConflictError(
            f"Expected project revision {expected_revision}, but current revision is {current['revision']}"
        )

    def _raise_line_update_error(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        line_id: UUID,
        user_id: int,
        expected_revision: int,
    ) -> None:
        """Classify why the conditional line update changed no rows."""
        cur.execute(
            """
            SELECT line.revision, line.audio_status
            FROM dialogue_lines AS line
            JOIN editor_projects AS project ON project.id = line.project_id
            WHERE line.id = %s AND line.project_id = %s AND project.user_id = %s
            """,
            (line_id, project_id, user_id),
        )
        current = cur.fetchone()
        if current is None:
            raise EditorProjectNotFoundError("Editor project or dialogue line not found")
        if current["audio_status"] == "generating":
            raise EditorLineGeneratingError(
                "Dialogue cannot be edited while audio is generating"
            )
        raise EditorRevisionConflictError(
            f"Expected revision {expected_revision}, but current revision is {current['revision']}"
        )
