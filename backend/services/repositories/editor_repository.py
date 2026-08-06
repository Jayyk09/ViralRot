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


class EditorStaleCompositionError(EditorRevisionConflictError):
    """Raised when visual work targets a composition that is no longer active."""


class EditorTimelineOverlapError(EditorClipValidationError):
    """Raised when generated replacement placements overlap one another."""


class EditorVisualLifecycleError(Exception):
    """Raised when an invalid generated-visual lifecycle transition is requested."""


class MediaAssetLimitError(Exception):
    """Raised when a project has reached its media asset quota."""


class MediaAssetInUseError(Exception):
    """Raised when deleting a media asset that timeline clips still reference."""

    def __init__(self, referencing_clip_ids: List[UUID]):
        self.referencing_clip_ids = [str(clip_id) for clip_id in referencing_clip_ids]
        super().__init__(
            f"Media asset is referenced by {len(referencing_clip_ids)} timeline clip(s)"
        )


class GeneratedTimelinePlacement(TypedDict):
    """A successfully ingested visual ready for fixed timeline placement."""

    asset_id: UUID
    start_ms: int
    end_ms: int


# Geometry tolerance: the editor clamps interactively, so only float rounding
# should ever push x + width past 1.
_GEOMETRY_EPSILON = 0.001
_MAX_MEDIA_ASSETS_PER_PROJECT = 20
_GENERATED_MAX_FRAME_WIDTH = 0.6
_GENERATED_TOP_MARGIN = 0.05
_OUTPUT_WIDTH_PX = 1080
_OUTPUT_HEIGHT_PX = 1920


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


def generated_clip_geometry(
    asset_width_px: int, asset_height_px: int
) -> tuple[float, float, float]:
    """Return the fixed top-anchored geometry used by generated visuals.

    Generated images preserve their intrinsic aspect ratio, occupy at most 60%
    of the output width, and shrink further when needed to fit the full height.

    Horizontally centered, but anchored near the top rather than the exact
    vertical center: captions (both box and karaoke) always render at the
    frame's vertical center, so a dead-centered image would sit directly
    behind the caption text. A top margin keeps most images clear of that
    band; only an image tall enough to fill the whole frame height (no room
    left above) still reaches it, which is an unavoidable physical overlap
    rather than a placement choice.
    """
    if asset_width_px <= 0 or asset_height_px <= 0:
        raise EditorClipValidationError("Asset dimensions must be positive")

    width_to_fit_height = (
        (asset_width_px / asset_height_px) * (_OUTPUT_HEIGHT_PX / _OUTPUT_WIDTH_PX)
    )
    width = min(_GENERATED_MAX_FRAME_WIDTH, width_to_fit_height)
    height = width * (asset_height_px / asset_width_px) * (
        _OUTPUT_WIDTH_PX / _OUTPUT_HEIGHT_PX
    )
    x = (1.0 - width) / 2.0
    y = min(_GENERATED_TOP_MARGIN, max(0.0, 1.0 - height))
    validate_clip_geometry(x, y, width, asset_width_px, asset_height_px)
    return x, y, width


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

    def list_projects(
        self, user_id: int, offset: int = 0, limit: int = 50
    ) -> List[Dict[str, object]]:
        """List lightweight summaries for projects owned by one user."""
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT project.id, project.title, project.background_video_id,
                           project.revision, project.created_at, project.updated_at,
                           (project.active_composition_id IS NOT NULL) AS narration_ready,
                           COUNT(DISTINCT line.id)::integer AS dialogue_count,
                           COUNT(DISTINCT video.id)::integer AS export_count,
                           MAX(video.created_at) AS latest_export_at
                    FROM editor_projects AS project
                    LEFT JOIN dialogue_lines AS line
                      ON line.project_id = project.id
                    LEFT JOIN videos AS video
                      ON video.editor_project_id = project.id
                     AND video.user_id = project.user_id
                    WHERE project.user_id = %s
                    GROUP BY project.id
                    ORDER BY project.updated_at DESC, project.id DESC
                    OFFSET %s LIMIT %s
                    """,
                    (user_id, offset, limit),
                )
                return [dict(row) for row in cur.fetchall()]
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

    def capture_active_composition(
        self, project_id: UUID, user_id: int
    ) -> Dict[str, object]:
        """Capture the owned project's active narration for visual planning.

        The returned composition id is the concurrency token for every later
        visual-generation step. Its manifest contains the finalized ordered
        captions and timing boundaries used to resolve planner line indexes.
        """
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT project.id AS project_id, project.title,
                           project.revision AS project_revision,
                           composition.id AS composition_id,
                           composition.duration_ms,
                           composition.line_manifest
                    FROM editor_projects AS project
                    LEFT JOIN audio_compositions AS composition
                      ON composition.id = project.active_composition_id
                    WHERE project.id = %s AND project.user_id = %s
                    """,
                    (project_id, user_id),
                )
                snapshot = cur.fetchone()
                if snapshot is None:
                    raise EditorProjectNotFoundError("Editor project not found")
                if snapshot["composition_id"] is None:
                    raise EditorCompositionRequiredError(
                        "Generate narration before planning visuals"
                    )
                result = dict(snapshot)
                result["line_manifest"] = result["line_manifest"] or []
                return result
        finally:
            conn.close()

    def verify_active_composition(
        self,
        project_id: UUID,
        user_id: int,
        expected_composition_id: UUID,
    ) -> Dict[str, object]:
        """Verify a captured composition is still active and return its snapshot."""
        try:
            snapshot = self.capture_active_composition(project_id, user_id)
        except EditorCompositionRequiredError as exc:
            raise EditorStaleCompositionError(
                "The active narration changed while visuals were generating"
            ) from exc
        if snapshot["composition_id"] != expected_composition_id:
            raise EditorStaleCompositionError(
                "The active narration changed while visuals were generating"
            )
        return snapshot

    def preflight_media_asset_quota(
        self, project_id: UUID, user_id: int, required_assets: int
    ) -> int:
        """Require capacity for an ingestion batch and return remaining capacity.

        This is deliberately a preflight rather than a reservation. Each later
        asset insert still enforces the quota while holding the project lock.
        """
        if required_assets < 0:
            raise EditorVisualLifecycleError("required_assets cannot be negative")

        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id FROM editor_projects WHERE id = %s AND user_id = %s",
                    (project_id, user_id),
                )
                if cur.fetchone() is None:
                    raise EditorProjectNotFoundError("Editor project not found")
                cur.execute(
                    "SELECT COUNT(*) AS count FROM media_assets WHERE project_id = %s",
                    (project_id,),
                )
                current_count = int(cur.fetchone()["count"])
                available = max(0, _MAX_MEDIA_ASSETS_PER_PROJECT - current_count)
                if required_assets > available:
                    raise MediaAssetLimitError(
                        f"Project has capacity for {available} more image(s), "
                        f"but {required_assets} are required"
                    )
                return available
        finally:
            conn.close()

    def get_manual_timeline_occupancy(
        self, project_id: UUID, user_id: int
    ) -> List[Dict[str, object]]:
        """Return current half-open time ranges occupied by owned manual clips."""
        conn = get_db_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id FROM editor_projects WHERE id = %s AND user_id = %s",
                    (project_id, user_id),
                )
                if cur.fetchone() is None:
                    raise EditorProjectNotFoundError("Editor project not found")
                return self._manual_timeline_occupancy(cur, project_id)
        finally:
            conn.close()

    def replace_generated_timeline_clips(
        self,
        project_id: UUID,
        user_id: int,
        expected_composition_id: UUID,
        placements: List[GeneratedTimelinePlacement],
    ) -> Dict[str, object]:
        """Atomically replace every still-generated clip after a successful run.

        The caller must not invoke this for an empty plan, cancellation, or total
        ingestion failure. Manual clips and all media assets survive. Placements
        newly overlapping a manual clip are omitted, while the successful asset
        remains in the project media library.
        """
        normalized = self._normalize_generated_placements(placements)
        if not normalized:
            raise EditorVisualLifecycleError(
                "Generated clip replacement requires at least one successful placement"
            )
        self._validate_generated_placement_overlaps(normalized)

        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # This project row lock serializes composition activation,
                    # manual clip writes (which take FOR SHARE), clip creation,
                    # and this final replacement without holding a transaction
                    # during provider or image work.
                    cur.execute(
                        """
                        SELECT id, revision, active_composition_id
                        FROM editor_projects
                        WHERE id = %s AND user_id = %s
                        FOR UPDATE
                        """,
                        (project_id, user_id),
                    )
                    project = cur.fetchone()
                    if project is None:
                        raise EditorProjectNotFoundError("Editor project not found")
                    if project["active_composition_id"] != expected_composition_id:
                        raise EditorStaleCompositionError(
                            "The active narration changed while visuals were generating"
                        )

                    cur.execute(
                        """
                        SELECT id, duration_ms
                        FROM audio_compositions
                        WHERE id = %s AND project_id = %s
                        """,
                        (expected_composition_id, project_id),
                    )
                    composition = cur.fetchone()
                    if composition is None:
                        raise EditorStaleCompositionError(
                            "The captured narration composition is no longer available"
                        )

                    manual_clips = self._manual_timeline_occupancy(
                        cur, project_id, for_update=True
                    )
                    asset_ids = list({placement["asset_id"] for placement in normalized})
                    cur.execute(
                        """
                        SELECT id, width_px, height_px
                        FROM media_assets
                        WHERE project_id = %s AND user_id = %s
                          AND status = 'ready' AND id = ANY(%s)
                        FOR SHARE
                        """,
                        (project_id, user_id, asset_ids),
                    )
                    assets = {row["id"]: row for row in cur.fetchall()}
                    if len(assets) != len(asset_ids):
                        raise EditorProjectNotFoundError(
                            "One or more generated media assets were not found"
                        )

                    duration_ms = int(composition["duration_ms"])
                    insertable: List[Dict[str, object]] = []
                    for placement in normalized:
                        start_ms, end_ms = self._validate_generated_placement_window(
                            placement["start_ms"], placement["end_ms"], duration_ms
                        )
                        if any(
                            self._timeline_windows_overlap(
                                start_ms,
                                end_ms,
                                int(manual["start_ms"]),
                                int(manual["end_ms"]),
                            )
                            for manual in manual_clips
                        ):
                            continue

                        asset = assets[placement["asset_id"]]
                        x, y, width = generated_clip_geometry(
                            int(asset["width_px"]), int(asset["height_px"])
                        )
                        insertable.append(
                            {
                                "asset_id": placement["asset_id"],
                                "start_ms": start_ms,
                                "end_ms": end_ms,
                                "x": x,
                                "y": y,
                                "width": width,
                            }
                        )

                    if insertable:
                        highest_manual_z = max(
                            (int(clip["z_index"]) for clip in manual_clips),
                            default=-1,
                        )
                        generated_z_index = highest_manual_z + 1
                        if generated_z_index > 1000:
                            raise EditorVisualLifecycleError(
                                "No visual layer is available above the manual clips"
                            )
                        validate_z_index(generated_z_index)
                    else:
                        generated_z_index = 0

                    cur.execute(
                        "DELETE FROM timeline_clips "
                        "WHERE project_id = %s AND origin = 'generated'",
                        (project_id,),
                    )
                    for placement in insertable:
                        cur.execute(
                            """
                            INSERT INTO timeline_clips
                                (id, project_id, asset_id, start_ms, end_ms,
                                 x, y, width, z_index, authored_composition_id,
                                 timing_status, origin)
                            VALUES
                                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                 'aligned', 'generated')
                            """,
                            (
                                uuid4(),
                                project_id,
                                placement["asset_id"],
                                placement["start_ms"],
                                placement["end_ms"],
                                placement["x"],
                                placement["y"],
                                placement["width"],
                                generated_z_index,
                                expected_composition_id,
                            ),
                        )

                    self._advance_project_revision_keep_composition(
                        cur, project_id, user_id
                    )
                    return self._get_project(cur, project_id, user_id)
        finally:
            conn.close()

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
                    if cur.fetchone()["count"] >= _MAX_MEDIA_ASSETS_PER_PROJECT:
                        raise MediaAssetLimitError(
                            f"A project can contain at most "
                            f"{_MAX_MEDIA_ASSETS_PER_PROJECT} images"
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

        Any persisted edit makes the clip manual so later visual generation
        cannot replace a user-adjusted clip. Swapping asset_id preserves
        geometry/timing (only provided fields change). Retiming re-authors the
        clip against the active composition and clamps to its duration;
        geometry-only edits leave timing fields and timing_status untouched.
        """
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Serialize against composition activation so a retime uses
                    # one stable active composition. Activation itself leaves
                    # visual clips untouched.
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
                               clip.origin, clip.revision,
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
                            origin = 'manual', revision = revision + 1,
                            updated_at = NOW()
                        WHERE id = %s AND revision = %s
                        RETURNING id, project_id, asset_id, start_ms, end_ms, x, y,
                                  width, z_index, authored_composition_id,
                                  timing_status, origin, revision, created_at, updated_at
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

    def _manual_timeline_occupancy(
        self,
        cur: RealDictCursor,
        project_id: UUID,
        for_update: bool = False,
    ) -> List[Dict[str, object]]:
        lock_clause = " FOR UPDATE" if for_update else ""
        cur.execute(
            """
            SELECT id, start_ms, end_ms, z_index
            FROM timeline_clips
            WHERE project_id = %s AND origin = 'manual'
            ORDER BY start_ms, end_ms, id
            """
            + lock_clause,
            (project_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def _normalize_generated_placements(
        self, placements: List[GeneratedTimelinePlacement]
    ) -> List[Dict[str, object]]:
        normalized: List[Dict[str, object]] = []
        for placement in placements:
            try:
                raw_asset_id = placement["asset_id"]
                start_ms = placement["start_ms"]
                end_ms = placement["end_ms"]
            except (KeyError, TypeError) as exc:
                raise EditorVisualLifecycleError(
                    "Every generated placement requires asset_id, start_ms, and end_ms"
                ) from exc

            try:
                asset_id = (
                    raw_asset_id
                    if isinstance(raw_asset_id, UUID)
                    else UUID(str(raw_asset_id))
                )
            except (TypeError, ValueError, AttributeError) as exc:
                raise EditorVisualLifecycleError(
                    "Generated placement asset_id must be a UUID"
                ) from exc
            if (
                not isinstance(start_ms, int)
                or isinstance(start_ms, bool)
                or not isinstance(end_ms, int)
                or isinstance(end_ms, bool)
            ):
                raise EditorClipValidationError(
                    "Generated placement times must be integer milliseconds"
                )
            if start_ms < 0:
                raise EditorClipValidationError("start_ms must be at least 0")
            if end_ms <= start_ms:
                raise EditorClipValidationError("end_ms must be greater than start_ms")
            if end_ms - start_ms < 500:
                raise EditorClipValidationError(
                    "Visual clips must be at least 0.5 seconds long"
                )
            normalized.append(
                {"asset_id": asset_id, "start_ms": start_ms, "end_ms": end_ms}
            )
        return normalized

    def _validate_generated_placement_overlaps(
        self, placements: List[Dict[str, object]]
    ) -> None:
        ordered = sorted(
            placements,
            key=lambda placement: (placement["start_ms"], placement["end_ms"]),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if self._timeline_windows_overlap(
                int(previous["start_ms"]),
                int(previous["end_ms"]),
                int(current["start_ms"]),
                int(current["end_ms"]),
            ):
                raise EditorTimelineOverlapError(
                    "Generated replacement placements must not overlap"
                )

    def _validate_generated_placement_window(
        self, start_ms: int, end_ms: int, duration_ms: int
    ) -> tuple[int, int]:
        if start_ms >= duration_ms:
            raise EditorClipValidationError(
                f"start_ms {start_ms} is beyond the narration duration {duration_ms}"
            )
        if end_ms > duration_ms:
            raise EditorClipValidationError(
                f"end_ms {end_ms} is beyond the narration duration {duration_ms}"
            )
        # Basic range and minimum checks were done before opening the
        # transaction; retain this call as the final timing trust-boundary
        # validation against the locked composition.
        return clamp_clip_window(start_ms, end_ms, duration_ms)

    @staticmethod
    def _timeline_windows_overlap(
        first_start_ms: int,
        first_end_ms: int,
        second_start_ms: int,
        second_end_ms: int,
    ) -> bool:
        """Return whether two half-open timeline windows intersect."""
        return first_start_ms < second_end_ms and second_start_ms < first_end_ms

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
                   z_index, authored_composition_id, timing_status, origin,
                   revision, created_at, updated_at
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
                    # Narration activation is audio-only. Existing clips retain
                    # their timing, composition binding, status, and revision
                    # until explicit visual regeneration or a manual edit.
        finally:
            conn.close()

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
