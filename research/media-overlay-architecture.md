# Timeline-Native Image/Media Overlays for the ViratRot Editor

**Status:** Research / architecture proposal — no application code changed.
**Date:** 2026-05 (repo state at time of writing)
**Scope:** How to add image (and later, other media) overlays that live on the *project timeline* — explicitly **not** attached to dialogue lines — covering data model, upload lifecycle, storage, API, preview, export, concurrency, GC, security, and an incremental MVP path.

Claims are labeled:

- **[code]** — verified by reading this repository.
- **[sourced]** — verified against a primary source (cited).
- **[rec]** — my recommendation / judgment, not an external convention.

---

## 1. What exists today (code inspection)

### 1.1 Frontend editor & canvas renderer

- The persisted editor model is `EditorProject { revision, dialogue: EditorLineRecord[], active_composition, exports }` (`frontend/lib/types.ts`). **[code]**
- There is a **vestigial line-attached image model**: `DialogueLine.images?: ImageConfig[]` where `ImageConfig = { filename, x, y, width, presignedUrl? }` in canvas pixels. It is *frontend-only dead weight right now*: `Editor.tsx` passes `placingImage={null}` and no-op `onImagePlaced/onUpdateImage/onDeleteImage` handlers, the "Add visual" tool button is `disabled`, and **the backend never persists images** — `dialogue_lines` has no image column and `EditorLineInput` accepts only `caption/speaker/emotion`. **[code]**
  - Consequence: there is **no data migration burden**. The user's constraint ("no images on dialogue lines") is satisfiable by building the new model cleanly and deleting the dead `DialogueLine.images` path later.
- Rendering is layer-based (`CanvasRenderer` with `VideoLayer` z=?, `ImageOverlayLayer` z=10, `CaptionLayer`), fixed internal canvas of **1080×1920 @ 30fps** matching the FFmpeg output (`DEFAULT_RENDERER_CONFIG`). **[code]**
- Playback clock: a hidden `<audio>` element playing the **active composition** is the master clock (`use-canvas-renderer.ts`). Every frame, the hook resolves the active line from absolute `line_timings`, prepares layers per line-segment, and calls `renderer.seek(t - segment.startTime)` — so **layers receive segment-local time**, but each `SegmentData` carries its absolute `startTime`, so a layer can reconstruct absolute time (`segment.startTime + time`). **[code]**
- Precedent for project-level (non-segment) data inside a layer: `CaptionLayer.setAbsoluteWordTimestamps(...)` is fed absolute word timings outside the segment mechanism. This is exactly the injection pattern a timeline-native overlay layer should use. **[code]**
- `ImageOverlayEditor.tsx` already implements freeform drag/resize in **canvas-pixel coordinates** (top-left anchor, width-only sizing, aspect ratio derived from the image's natural dimensions, `MIN_WIDTH=80`, `MAX_WIDTH=900`), converting screen↔canvas via bounding-rect scaling. **[code]**
- `EditorFooter.tsx` renders a timeline with a **"Visual" track row that is currently just a static background label** and a per-line "Voice" track whose block widths are proportional to real `line_timings` durations. This is the natural UI home for overlay clips. **[code]**

### 1.2 Postgres editor schema & repository

`backend/scripts/create_editor_tables.sql` + `services/repositories/editor_repository.py`: **[code]**

- `editor_projects(id, user_id, title, background_video_id, revision ≥ 1, active_composition_id → audio_compositions ON DELETE SET NULL)`.
- `dialogue_lines(id, project_id CASCADE, position, caption, speaker, emotion, revision, audio_status ∈ {missing, generating, ready, stale, failed}, audio_error, active_segment_id → audio_segments ON DELETE SET NULL, UNIQUE(project_id, position) DEFERRABLE)`.
- `audio_segments` / `audio_compositions`: **immutable artifact rows** (unique `storage_key`, never updated) with a mutable "active" pointer on the owning row. Composition carries an absolute-time `line_manifest` (`line_id, segment_id, start_ms, end_ms, caption, speaker, emotion`).
- Concurrency pattern: per-entity `revision` + `expected_revision` conditional `UPDATE`; project-level structural ops take `SELECT ... FOR UPDATE` on the project row (`_lock_project`), then `SET CONSTRAINTS ... DEFERRED` for position shuffles; conflicts surface as 409.
- **Critical detail for overlays:** two different "bump the project" helpers exist:
  - `_advance_project_revision` → `revision+1` **and nulls `active_composition_id`** (used by add/delete/reorder lines — anything that changes narration).
  - `update_project` (title/background) → `revision+1` **without** touching the composition, with an explicit frontend comment that project-only edits "must not invalidate audio."
  Overlay mutations are visual-only and must follow the second pattern; reusing `_advance_project_revision` would silently force narration regeneration for a purely visual edit. **[code]**

### 1.3 Storage abstraction

`storage/base.py` defines `StorageBackend` with `upload / generate_url / generate_background_urls / download / iter_keys / delete / exists / get_size / list_files / get_stats`. **[code]**

- `R2StorageBackend` uses boto3 SigV4 against `https://{account_id}.r2.cloudflarestorage.com`, path-style addressing, checksum workarounds for R2, and already issues **presigned GET** URLs (`generate_presigned_url("get_object", ExpiresIn=3600)`). There is **no presigned PUT / upload-URL capability in the abstraction today.** **[code]**
- `LocalStorageBackend.generate_url` returns **`file://` URLs, which a browser cannot fetch** — local dev cannot presign, and cannot even serve overlay images to the canvas without a new HTTP route. (The `ENABLE_DEV_FIXTURES` `StaticFiles` mount in `main.py` is the existing precedent for HTTP-serving local files.) **[code]**
- Key conventions: narration artifacts at `editor/{user_id}/{project_id}/segments/{segment_id}.mp3` and `.../compositions/{composition_id}.mp3`; exported videos at `{user_id}/{uuid}.mp4`. Keys are always server-generated. **[code]**
- `storage/assets.py` implements a download cache (`tmp/asset_cache`, `.partial` rename) for pipeline assets — reusable for overlay images at export time. **[code]**
- **There is no garbage collection anywhere**: superseded segments/compositions accumulate in storage and DB; deletes happen only on inline failure compensation (`EditorAudioService` deletes the just-uploaded key when the DB write fails). **[code]**

### 1.4 API patterns

`backend/main.py`: **[code]**

- JSON bodies validated by Pydantic; ownership enforced by `user_id` in every SQL predicate (auth is stubbed: `get_current_user_id() → 1`).
- Mutations carry `expected_revision` / `expected_project_revision`; 409 on conflict/invalid order; 404 wrapped from repository exceptions.
- Structural mutations return a **full project snapshot** `{"project": ...}`; line-scoped PATCH returns `{"line": ...}`.
- Long-running work is 202 + `job_id` + WebSocket/polling URLs via `ProgressService`; jobs run as FastAPI `BackgroundTasks` calling sync code through `asyncio.to_thread`.
- `_editor_project_response` attaches **fresh presigned URLs at read time** (composition audio, export videos) — URLs are never persisted, only keys. Overlay asset URLs should follow this exactly.

### 1.5 Audio composition timing

- `EditorAudioService.generate_narration` claims stale/missing lines (`prepare_audio_generation` flips them to `generating`), TTS-es each line, uploads immutable segments, then concatenates **end-to-end with no gaps** (ffmpeg concat demuxer, `-c copy`) and computes absolute `start/end` per line by summing durations (`concatenate_audio_segments` in `minimax_tts.py`). The manifest is absolute milliseconds on the project timeline. **[code]**
- Therefore: **editing any line's text re-times every subsequent line** the next time narration is regenerated. Any overlay timing model must answer "what happens to a clip at 12.4s when the narration around 12.4s moves." **[code — consequence]**

### 1.6 FFmpeg export pipeline

`backend_pipeline/video_assembly/ffMpeg.py`: **[code]**

- `create_video_with_audio_and_captions` **already supports timed image overlays** via the `educational_images` parameter: each entry is `{path, size, position, start, end}`; images are added as `-loop 1 -i <path>` inputs, scaled with `scale={width}:-1`, and composited with `overlay=x=..:y=..:enable='between(t,start,end)'`, chained through `[tmp_N]` intermediates. Consecutive same-image windows are merged to prevent flicker.
- **But** its geometry model is preset-based (`small/medium/large` × named positions like `top-right`, producing FFmpeg *expressions* like `W-w-50`) — it cannot express the frontend's freeform `x/y/width`. A freeform variant is a small, additive change (numeric `x`, `y`, `scale=width:-1`), not a rework.
- The editor export job (`_process_project_video_job`) currently passes `educational_images=None`, renders strictly from the **active composition manifest** (downloads composition audio by key, never re-invokes TTS), and truncates output at audio duration (`-t audio_duration`). It re-reads the project **once** at job start — a snapshot-by-read, with a small TOCTOU window between the 202 response and the read.

---

## 2. Sourced conventions (primary sources)

### 2.1 OpenTimelineIO — how the industry models "asset vs clip"

From the OTIO 0.18.1 documentation ([Timeline Structure](https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-timeline-structure.html), [Time Ranges](https://opentimelineio.readthedocs.io/en/stable/tutorials/time-ranges.html)): **[sourced]**

- A `Timeline` holds a top-level `Stack` of `Track`s; tracks hold `Clip`s, `Gap`s, `Transition`s, and nested compositions.
- **A `Clip` is placement; a `MediaReference` is the asset.** The media reference carries `target_url` (file path or network URL) and an optional `available_range`; the clip's `source_range` trims it. A clip may even reference media that doesn't (yet) satisfy its range — "OTIO itself does no snapping or verification."
- **Within a track, position is implicit and sequential**: `clipA.range_in_parent().end_time_exclusive() == clipB.range_in_parent().start_time`. Offsetting a clip is done by inserting a `Gap` before it (or trimming the track's `source_range`). There are no absolute start times stored on clips.
- **Overlay layering is painter order**: stacks render bottom→top with alpha compositing; a separate video track above the base track is the canonical way to model overlays.
- Times are `RationalTime(value, rate)` — rate-aware rational times, not float seconds.

Two takeaways worth stating precisely:

1. The **asset/clip split is an industry-standard separation** — adopt it.
2. OTIO's *sequential* track model gives ripple-on-edit within a track for free, but says **nothing about cross-track ripple**: a clip on an overlay track does not automatically move when a clip on the narration track changes length. Applications decide that behavior. So "what happens to overlays when narration re-times" is a **product decision**, not something a standard resolves for you. **[sourced + analysis]**

### 2.2 FFmpeg — overlay + timeline enable

From the FFmpeg filters documentation ([ffmpeg-filters.html](https://ffmpeg.org/ffmpeg-filters.html), overlay §, Timeline editing §, scale §): **[sourced]**

- `overlay` takes two inputs (main + overlaid); `x`/`y` accept expressions with `main_w/W`, `main_h/H`, `overlay_w/w`, `overlay_h/h`, and `t` (seconds); default `eval=frame` re-evaluates per frame.
- Filters supporting *timeline editing* accept a generic `enable` expression evaluated per frame — e.g. `enable='between(t,10,180)'`; non-matching frames pass through unchanged. This is exactly what the existing pipeline uses.
- "You can chain together more overlays but you should test the efficiency of such approach" — chained overlays (the current `[tmp_N]` pattern) are the documented approach, with an explicit performance caveat that motivates a cap on simultaneous overlay count.
- `scale=w:-1` — "If one and only one of the values is `-n` with n ≥ 1, the scale filter will use a value that maintains the aspect ratio of the input image." So storing width only and deriving height from intrinsic aspect is faithful on both canvas (`drawImage` with computed height — the existing `ImageOverlayLayer` does this) and FFmpeg sides.
- Inputs to `overlay` should start at aligned timestamps (`setpts=PTS-STARTPTS` guidance) — the existing pipeline already normalizes the background with `setpts`.

### 2.3 Cloudflare R2 — presigned uploads

From [Cloudflare R2: Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/): **[sourced]**

- R2 presigned URLs support **GET, HEAD, PUT, DELETE**. **`POST` (HTML multipart form upload) is not supported.** Consequence: S3 *POST policy* conditions — including `content-length-range`, the standard way to cap upload size at the storage layer (AWS S3 API reference, [POST Policy construction](https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-HTTPPOSTConstructPolicy.html)) — are **unavailable on R2**. A presigned PUT cannot enforce a maximum object size by itself, so size must be validated after upload (HEAD/`get_size`) and oversized objects deleted. **[sourced + analysis]**
- Expiry is 1 second – 7 days (604,800 s); URLs are generated fully client-side (no R2 round trip) with SigV4.
- **`ContentType` can be baked into the signature** (boto3: `generate_presigned_url('put_object', Params={'Bucket','Key','ContentType'})`); a client sending a different `Content-Type` gets `403 SignatureDoesNotMatch`. Cloudflare's own "best practices" list this plus **configuring bucket CORS** for browser use.
- Presigned URLs are **bearer tokens** — anyone holding one can perform the operation until expiry; Cloudflare recommends short expiries for sensitive operations.
- Presigned URLs work only on the `<ACCOUNT_ID>.r2.cloudflarestorage.com` S3 domain, **not custom domains**.
- AWS S3's presigned-PUT semantics (which R2 mirrors): the uploaded object silently **replaces** any existing object at that key — another reason keys must be server-generated and unique per upload session ([AWS S3: Uploading objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)). **[sourced]**

---

## 3. Recommended architecture

### 3.1 Entities: `media_assets` (file identity) vs `timeline_clips` (placement) **[rec, mirroring OTIO's sourced Clip/MediaReference split and the repo's segment/composition pattern]**

Two tables, following the codebase's own "immutable artifact + pointer + status machine" idiom:

- **`media_assets`** — one row per uploaded file. Owns the upload lifecycle (§3.3), storage key, validated metadata (bytes, content type, intrinsic width/height, checksum). Immutable once `ready` (like `audio_segments`). Deleting/replacing an image in the editor never mutates an asset's bytes — new upload ⇒ new asset ⇒ new key.
- **`timeline_clips`** — one row per placement of an asset on the project timeline: absolute `start_ms/end_ms`, normalized geometry, `z_index`, its own `revision` for autosave. Many clips may reference one asset (reuse without re-upload).

Why not one table? Because the failure domains differ (upload lifecycle vs editing lifecycle), reuse requires the split, GC reasons about assets (bytes) not clips (rows), and OTIO demonstrates the split is the durable industry shape.

### 3.2 Proposed SQL **[rec]**

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS media_assets (
    id                UUID PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Project-scoped for MVP. Make nullable later if a per-user library is wanted.
    project_id        UUID NOT NULL REFERENCES editor_projects(id) ON DELETE CASCADE,

    kind              TEXT NOT NULL DEFAULT 'image'
                          CHECK (kind IN ('image')),          -- future: 'video', 'audio'
    -- Server-generated; set at session creation, object may not exist yet.
    storage_key       TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,                          -- display only, never a path
    content_type      TEXT NOT NULL
                          CHECK (content_type IN ('image/png','image/jpeg','image/webp')),

    -- Populated at finalize (validated server-side, not trusted from client):
    byte_size         BIGINT  CHECK (byte_size IS NULL OR byte_size > 0),
    width_px          INTEGER CHECK (width_px  IS NULL OR width_px  > 0),
    height_px         INTEGER CHECK (height_px IS NULL OR height_px > 0),
    checksum_sha256   TEXT,

    status            TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','uploaded','ready','failed','expired')),
    error             TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at          TIMESTAMPTZ,
    -- Tombstone for DB-driven GC (see §3.8); bytes deleted by sweeper, then row.
    deleted_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_media_assets_project
    ON media_assets(project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_media_assets_gc
    ON media_assets(status, created_at)
    WHERE status IN ('pending','uploaded','failed','expired') OR deleted_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS timeline_clips (
    id            UUID PRIMARY KEY,
    project_id    UUID NOT NULL REFERENCES editor_projects(id) ON DELETE CASCADE,
    -- RESTRICT: an asset referenced by any clip cannot be hard-deleted.
    asset_id      UUID NOT NULL REFERENCES media_assets(id) ON DELETE RESTRICT,

    -- Absolute time on the project/composition timeline, in ms (matches line_manifest).
    start_ms      INTEGER NOT NULL CHECK (start_ms >= 0),
    end_ms        INTEGER NOT NULL,
    CONSTRAINT ck_timeline_clips_range CHECK (end_ms > start_ms),

    -- Normalized geometry, fraction of the output frame (see §3.5).
    -- Top-left anchor; height derived from asset aspect (canvas + scale=w:-1 agree).
    x             DOUBLE PRECISION NOT NULL CHECK (x >= 0 AND x <= 1),
    y             DOUBLE PRECISION NOT NULL CHECK (y >= 0 AND y <= 1),
    width         DOUBLE PRECISION NOT NULL CHECK (width > 0 AND width <= 1),
    z_index       INTEGER NOT NULL DEFAULT 0,

    -- Which narration timeline the times were authored against (ripple, §3.6).
    authored_composition_id UUID REFERENCES audio_compositions(id) ON DELETE SET NULL,
    timing_status TEXT NOT NULL DEFAULT 'aligned'
                      CHECK (timing_status IN ('aligned','needs_review')),

    -- Optimistic concurrency for autosaved geometry/time edits (mirrors dialogue_lines).
    revision      INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_timeline_clips_project_start
    ON timeline_clips(project_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_timeline_clips_asset
    ON timeline_clips(asset_id);

COMMIT;
```

Notes:

- `start_ms/end_ms` as `INTEGER` ms matches `audio_compositions.line_manifest` and `duration_ms` **[code]**. OTIO's rational-time model **[sourced]** is more general, but this project has a single fixed clock (the composition audio) and ms everywhere; introducing rational time would be gratuitous. **[rec]**
- No `UNIQUE(project_id, z_index)`: overlapping clips at equal z are fine; painter order = `ORDER BY z_index, created_at` (OTIO painter-order convention **[sourced]**, tie-break **[rec]**).
- Storage key convention (follows existing narration keys **[code]**): `editor/{user_id}/{project_id}/images/{asset_id}.{ext}` with the extension derived from the validated content type, never from the client filename. **[rec]**

### 3.3 Upload session lifecycle & state transitions

The `media_assets.status` column *is* the upload session (no separate sessions table needed at this scale — one upload per asset row). **[rec]**

```
                    POST /assets  (create session; server picks key; issues
                    presigned PUT (R2) or proxy target (local); status=pending)
                       │
                       ▼
   ┌──────────── pending ────────────┐
   │ client PUTs bytes               │  TTL exceeded (e.g. 1h) without finalize
   │ (direct to R2, or proxy route)  │──────────────────────────► expired
   ▼                                                              (sweeper deletes
 uploaded  ◄─ (proxy route sets this; for direct PUT the           object if present,
   │           server can't observe it — finalize probes)          then row)
   │ POST /assets/{id}/finalize:
   │   HEAD object (exists? size ≤ cap?)
   │   fetch head bytes → magic-byte sniff matches content_type?
   │   decode (Pillow verify) → width/height; checksum
   ├─ all pass ──► ready  (immutable from here on; usable by clips)
   └─ any fail ──► failed (server deletes object immediately; error recorded)

 ready ─ user deletes & no clip references ──► deleted_at set (tombstone)
                                               └─ sweeper: storage.delete(key) → drop row
```

Rationale for a mandatory **finalize** step: with a direct presigned PUT the server never sees the bytes, and R2 cannot enforce a size cap in the signature (no POST policy support **[sourced]**, §2.3) — so the server *must* probe (`exists`/`get_size` already exist on `StorageBackend` **[code]**) and validate before the asset becomes referenceable. Finalize is also the natural idempotency point: repeated calls on a `ready` asset return the asset unchanged; finalize on `pending` with no object returns 409 "not uploaded yet."

### 3.4 Direct vs proxied upload

- **R2 (prod): direct browser PUT via presigned URL.** Sourced support: PUT presigning, ContentType pinned in the signature, CORS configured on the bucket, short expiry (recommend 15 min — bearer-token guidance) **[sourced]**. Keeps multi-MB image bytes off the FastAPI process (which runs TTS/FFmpeg jobs in the same event loop's thread pool **[code]**).
- **Local (dev): proxied multipart upload** to a FastAPI route that calls `storage.upload(...)`. Local storage cannot presign and its `file://` URLs are browser-useless **[code]**, so a proxy is structurally required in dev anyway. Serving also needs a dev HTTP route (extend the `StaticFiles` precedent, or a `GET .../assets/{id}/content` passthrough). **[rec]**
- Unify behind the session response: `POST /assets` returns an `upload` descriptor whose `mode` is `"presigned_put"` or `"proxy"`; the frontend branches on `mode`, everything else identical. Add one optional capability method to `StorageBackend` (e.g. `generate_upload_url(key, content_type, expires_in) -> Optional[str]`, returning `None` for local) rather than forking service code on backend type. **[rec]**
- **MVP shortcut worth considering:** ship proxy-only first (works identically on both backends, one code path, size cap trivially enforced by the server as it streams), and add presigned direct upload in phase 2. Image overlays are ≤ a few MB; proxying is not a real bottleneck at current scale. **[rec]**

### 3.5 Geometry: normalized floats, top-left anchor, width-only

- Store `x, y, width ∈ (0,1]` as fractions of the output frame; derive height from the asset's intrinsic aspect. Both render paths already agree on this derivation: canvas uses `naturalHeight/naturalWidth` **[code]**, FFmpeg uses `scale=w:-1` which "maintains the aspect ratio of the input image" **[sourced]**.
- Today both preview and export are hard-coded 1080×1920 **[code]**, so pixels would work — but normalization future-proofs output-resolution changes, makes values self-describing, and costs one multiply at each boundary: frontend converts editor pixels ↔ normalized at the API; export computes `px = round(n * frame_dim)` when building the filtergraph (or emits FFmpeg expressions like `x=main_w*0.25` — supported per overlay's expression variables **[sourced]** — though numeric literals are simpler to debug). **[rec]**
- Persist the asset's validated `width_px/height_px` so the timeline UI and server-side clamping never need to load the image to know its aspect. **[rec]**
- Validation on clip writes: reject `x + width > 1 + ε`; clamp `y` so at least a sliver is on-frame (the current editor clamps interactively **[code]**; the server should re-check because the API is the trust boundary). **[rec]**

### 3.6 Absolute timeline timing and ripple after narration changes

This is the hardest design point, so stating the constraint set explicitly:

- The user requires **timeline-native** clips: times are project-absolute, not per-line. **[requirement]**
- The narration timeline is *rebuilt* on regeneration; editing line 2 re-times lines 3..n (gapless concat **[code]**).
- OTIO offers no cross-track ripple convention — the sequential model ripples *within* a track only; overlay tracks in a stack do not move when another track changes. Behavior on re-time is application-defined. **[sourced]**

**Recommendation** — absolute ms as the single source of truth, plus a *deterministic, explainable* remap executed exactly once at composition activation:

1. Each clip stores `authored_composition_id` — the composition whose timeline its `start_ms/end_ms` refer to.
2. When `activate_composition` installs a new composition, the same transaction remaps each clip using both manifests as piecewise-linear timelines keyed by **line boundaries**:
   - Find the line interval(s) of the *old* manifest that contain `start_ms`/`end_ms`; express each endpoint as `(line_id, fraction_within_line)`.
   - Re-emit the endpoint in the *new* manifest at the same `(line_id, fraction)`.
   - Edge cases: anchor line deleted → snap to the position where that line used to sit (previous surviving line's end), set `timing_status='needs_review'`; endpoint beyond new total duration → clamp, mark `needs_review`; clip in a gap that no longer exists (line removed entirely) → keep proportional position of the whole timeline, mark `needs_review`.
3. Update `authored_composition_id` to the new composition and leave `timing_status='aligned'` when the remap was unambiguous.
4. The UI surfaces `needs_review` clips (e.g., amber outline on the Visual track) instead of silently moving or silently *not* moving them.

Why this and not the alternatives:

- **Pure absolute (no remap):** simplest, but after any narration edit every overlay is misaligned with the content it illustrates; the feature would feel broken the first time a user edits a line. **[rec: rejected as end-state, acceptable as MVP with `needs_review` flagging — see §5]**
- **Anchor clips to line IDs (`anchor_line_id + offset_ms`):** best alignment survival, but it *is* attachment to dialogue lines at the data-model level — explicitly ruled out by the user, and it breaks for clips spanning multiple lines. Note the nuance for the product owner: "anchoring for ripple" and "UX attachment" are separable concepts; the remap in (2) gets most of the alignment benefit *without* storing line references on clips. **[analysis]**
- **OTIO-style sequential overlay track with gaps:** would ripple only against *its own* track, not against narration, so it doesn't actually solve this problem, and it's a much bigger modeling change. **[sourced + analysis]**

Interaction with the existing invariants **[code]**: line edits already null `active_composition_id`; between invalidation and the next activation there is no current timeline, so clips keep their old-composition times and the preview is gated (`narrationReady`) exactly as today. The remap runs at the moment a new timeline exists — the only moment it *can* run.

### 3.7 Autosave & optimistic concurrency

Follow the existing split precisely **[code-pattern → rec]**:

- **Clip geometry/time PATCH** (drag, resize, retime): clip-scoped `expected_revision`, bumps only `timeline_clips.revision` — mirrors `update_line`'s per-line revision, and matches the frontend's 300–500 ms debounce idiom (`ImageOverlayEditor` DEBOUNCE_MS=300, `Editor.handleLineChange` 500 ms **[code]**). Does **not** touch project revision (two users dragging different clips shouldn't conflict; single-user today anyway).
- **Clip add / delete, asset delete**: project-scoped `expected_project_revision` with `_lock_project`, bump project revision — mirrors `add_line`/`delete_line`, returns the full project snapshot.
- **Never null `active_composition_id` from any clip/asset mutation.** Visual edits must not invalidate narration (the `update_project` precedent and the explicit frontend comment **[code]**). This needs a new "advance revision, keep composition" repository helper rather than reusing `_advance_project_revision`.
- 409 semantics identical to today: frontend catches, sets `saveStatus="conflict"`, calls `onConflict()` → full refetch. **[code]**

### 3.8 Export consistency & snapshots

- **Snapshot at job start, in one read**: extend the single project read in `_process_project_video_job` to also pull clips (only `timing_status='aligned'`… or all — product call, §6) joined with `ready` assets, *in the same repository call*, so the job never observes a torn state. Better still **[rec]**: materialize `{composition_id, line_manifest, clips:[{asset storage_key, start_ms, end_ms, x, y, width, z_index}]}` into the job record at request time (the 202 handler already reads the project to validate **[code]**), eliminating the 202→task TOCTOU window entirely.
- **Fetch by key, not by URL**: the export job must `storage.download(asset.storage_key, ...)` into the export dir (as it does for composition audio **[code]**), optionally through the `storage/assets.py` cache. Never render from presigned GET URLs — 1-hour expiry vs. queued/long renders. **[rec]**
- **Immutability makes preview == export**: assets are never overwritten after `ready` (new upload ⇒ new key), so the bytes the canvas previewed are byte-identical to what FFmpeg composites. This is the same guarantee `audio_segments` provides for narration. **[rec, code-pattern]**
- **Filtergraph**: reuse the existing chained-overlay machinery — per clip: `-loop 1 -i img.png`, `[k:v]scale={round(width*1080)}:-1[clip_i]`, `overlay=x={round(x*1080)}:y={round(y*1920)}:enable='between(t,{start_ms/1000},{end_ms/1000})'`, ordered by `z_index` (painter order **[sourced]**), inserted after character overlays and **before** captions so captions stay on top (matches canvas z: images z=10 < captions **[code]**). Clips whose window exceeds audio duration are harmless — output is truncated at `-t audio_duration` **[code]** — but clamp anyway for tidy filtergraphs. Cap simultaneous overlays (FFmpeg's chained-overlay efficiency caveat **[sourced]**); recommend a validation limit like ≤ 20 clips/project, ≤ 4 overlapping at any instant **[rec]**.

### 3.9 Deletion & orphan GC

Failure-mode inventory and the sweep that covers each: **[rec]**

| Orphan source | Detection | Action |
|---|---|---|
| Session created, browser never uploads | `status='pending'` and `created_at < now()-TTL` | mark `expired`; `storage.delete(key)` (no-op if absent); drop row |
| Direct PUT succeeded, finalize never called | same as above — the object *exists* but DB says `pending` | same; the delete reclaims the bytes |
| Finalize validation failed | `status='failed'` | object already deleted inline at finalize; sweeper drops old rows |
| User deletes an unreferenced asset | `deleted_at` tombstone | sweeper: `storage.delete(key)` then `DELETE` row |
| Asset referenced by clips | `ON DELETE RESTRICT` blocks hard delete | API returns 409 with referencing clip IDs; UI offers "remove N clips too" |
| Project deleted | `ON DELETE CASCADE` removes rows, **bytes remain** (same existing gap as narration segments **[code]**) | prefix sweep `editor/{user}/{project}/` for projects absent from DB |

- **DB-driven deletion (tombstones) over storage-driven anti-join** (`iter_keys` vs DB): the anti-join races in-flight `pending` uploads whose rows exist but whose semantics are transient, and it's O(bucket). Only use the prefix anti-join for the project-deletion case, restricted to keys older than a safety TTL. **[rec]**
- The sweeper also naturally extends to the **pre-existing** narration orphan problem (superseded segments/compositions accumulate today **[code]**) — same tombstone pattern, out of scope for the MVP.
- Sequencing rule everywhere: **delete bytes before dropping the row** (a keyless row is a bug you can see; an unrecorded object is invisible money). The codebase's compensation blocks already follow "DB failed ⇒ delete uploaded object" **[code]**; GC is the mirror image.

### 3.10 Security & validation

- **Key control**: keys are server-generated (`asset_id`-based); the client-supplied filename is stored only as display metadata (`original_filename`), never used in paths — extends the existing convention **[code]**. Presigned PUT replaces objects at the same key silently **[sourced]**, so unique per-session keys also prevent overwrite games.
- **Type allowlist**: `image/png`, `image/jpeg`, `image/webp`. Exclude SVG (script-bearing, and not a raster input the FFmpeg pipeline is set up for) and defer GIF (FFmpeg treats it as multi-frame; `-loop 1` still-image handling differs — product decision §6). ContentType pinned in the PUT signature (R2 enforces via `SignatureDoesNotMatch` **[sourced]**) *and* re-verified at finalize by magic-byte sniff + full decode (Pillow `verify()`/`open()`), because the signature only proves the *header* matched, not the bytes. **[rec]**
- **Size caps**: cannot be enforced by R2 presigned PUT (no POST policy **[sourced]**) ⇒ enforce at finalize via `get_size` (e.g. 10 MB) and delete violators; proxy mode enforces while streaming. Dimension caps (e.g. ≤ 4096×4096) protect both canvas memory and filtergraph cost. Per-project asset-count quota. **[rec]**
- **Access control**: every query keyed by `(project_id, user_id)` exactly like `EditorRepository` **[code]**. Presigned GETs for assets minted per response in `_editor_project_response`, same as composition audio **[code]**; treat as bearer tokens with the default 1 h expiry — the frontend already refetches the project on conflict/regen, which refreshes URLs. Note: real auth is stubbed (`user_id=1`) **[code]** — overlay endpoints inherit whatever auth lands later.
- **EXIF**: strip metadata at finalize (re-encode) or accept leaving it — the bytes end up baked into rendered video anyway; recommend stripping since assets are also served to the browser. **[rec]**

---

## 4. API surface (endpoints & payloads) **[rec — shaped to match existing conventions]**

All under the existing router, ownership via `get_current_user_id()`, errors: 404 (not found/owned), 409 (revision conflict, invalid state, referenced asset), 422 (validation).

### Assets

```
POST /editor/projects/{project_id}/assets                    → 201
  { "filename": "diagram.png", "content_type": "image/png", "byte_size": 482113 }
  ⇒ {
      "asset": { "id": "...", "status": "pending", ... },
      "upload": {
        "mode": "presigned_put" | "proxy",
        "url":  "https://<acct>.r2.cloudflarestorage.com/...X-Amz-..."   // presigned_put
                | "/editor/projects/{pid}/assets/{id}/content",          // proxy
        "headers": { "Content-Type": "image/png" },      // must match the signature
        "expires_at": "2026-05-01T12:15:00Z"
      }
    }

POST /editor/projects/{project_id}/assets/{asset_id}/content  (proxy mode only)
  multipart/form-data file field ⇒ { "asset": { "status": "uploaded", ... } }

POST /editor/projects/{project_id}/assets/{asset_id}/finalize → 200
  {}   // idempotent; probes storage, validates magic bytes/decodes, records w/h/size/checksum
  ⇒ { "asset": { "id", "status": "ready", "width_px": 1200, "height_px": 800,
                  "byte_size": 482113, "content_type": "image/png",
                  "access_url": "<fresh presigned GET>" } }
  409 if no object yet; asset → "failed" (+ object deleted) if validation fails.

GET    /editor/projects/{project_id}/assets                   → { "assets": [ ... ] }
DELETE /editor/projects/{project_id}/assets/{asset_id}        → 200 { "asset": {...,"deleted_at":...} }
  409 { "detail": "...", "referencing_clip_ids": [...] } if clips reference it.
```

### Clips

```
POST /editor/projects/{project_id}/clips                      → 201
  { "asset_id": "...", "start_ms": 12400, "end_ms": 18200,
    "x": 0.361, "y": 0.333, "width": 0.278, "z_index": 0,
    "expected_project_revision": 7 }
  ⇒ { "project": { ...full snapshot incl. "clips" and "assets"... } }
  422 unless the asset is status='ready' and geometry/time pass validation.
  Bumps project revision; DOES NOT invalidate active_composition_id.

PATCH /editor/projects/{project_id}/clips/{clip_id}           → 200
  { "start_ms": ..., "end_ms": ..., "x": ..., "y": ..., "width": ..., "z_index": ...,
    "expected_revision": 3 }                     // clip-scoped, debounced autosave
  ⇒ { "clip": { ... } }                          // mirrors update_line's {"line": ...}

DELETE /editor/projects/{project_id}/clips/{clip_id}
  { "expected_project_revision": 7 }             ⇒ { "project": {...} }
```

### Reads

`GET /editor/projects/{project_id}` gains two arrays, with URLs minted at read time like everything else **[code-pattern]**:

```jsonc
{
  "project": {
    ...,
    "assets": [ { "id", "status", "content_type", "width_px", "height_px",
                  "original_filename", "access_url" } ],
    "clips":  [ { "id", "asset_id", "start_ms", "end_ms", "x", "y", "width",
                  "z_index", "timing_status", "revision" } ]
  }
}
```

### Frontend type sketch

```ts
export interface MediaAsset {
  id: string; status: "pending"|"uploaded"|"ready"|"failed"|"expired";
  content_type: string; width_px: number|null; height_px: number|null;
  original_filename: string; access_url: string|null;
}
export interface TimelineClip {
  id: string; asset_id: string;
  start_ms: number; end_ms: number;          // absolute, composition timeline
  x: number; y: number; width: number;       // normalized 0..1
  z_index: number; revision: number;
  timing_status: "aligned" | "needs_review";
}
```

`ImageConfig` / `DialogueLine.images` get deleted once the new path lands (they persist nothing today **[code]**).

---

## 5. Incremental MVP migration path **[rec]**

**Phase 0 — schema + plumbing (no UI):**
`media_assets` + `timeline_clips` migration (idempotent style of `create_editor_tables.sql`); `MediaAssetRepository`/`TimelineClipRepository` following `EditorRepository` transaction idioms; the "advance revision without invalidating composition" helper; project GET includes empty `assets`/`clips`.

**Phase 1 — MVP (proxy upload, absolute time, flag-don't-remap):**
- Proxy upload + finalize (works identically on local and R2; direct PUT deferred). Dev image serving via passthrough/static route.
- Clip CRUD with the concurrency rules of §3.7.
- Preview: give `ImageOverlayLayer` a project-scoped `setClips(clips, assetUrlByAssetId)` (the `CaptionLayer.setAbsoluteWordTimestamps` injection pattern **[code]**); in `render(ctx, time)`, compute `absolute = segment.startTime + time` and draw clips where `start_ms/1000 ≤ absolute < end_ms/1000` — decoupling overlays from line segments entirely. Reuse `ImageOverlayEditor`'s drag/resize with a px↔normalized conversion at its edge.
- Timeline: render clip blocks on the existing "Visual" footer row positioned by `start_ms/end_ms` over composition duration; drag to move/trim time.
- Ripple: **no remap yet** — on `activate_composition`, set every clip's `timing_status='needs_review'` if any `start_ms/end_ms` would change meaning (i.e., whenever the manifest differs), render them amber, keep absolute times. Honest, cheap, unblocks shipping.
- Export: extend the export job snapshot with clips; add the freeform branch beside `educational_images` in `ffMpeg.py` (numeric x/y, `scale=w:-1`, `enable=between`), captions still last.

**Phase 2 — production hardening:**
Presigned direct PUT for R2 (+ bucket CORS config); deterministic line-boundary remap of §3.6 replacing flag-only behavior; GC sweeper (`cleanup` script first, scheduled later); quotas/size caps enforcement; z-index UI; delete `DialogueLine.images`/`ImageConfig` dead code.

**Phase 3 — extensions:** per-user asset library (`project_id` nullable), GIF/video overlay clips (different FFmpeg input handling: trim/loop of a video input rather than `-loop 1` still), opacity/rotation columns, music track (the footer already stubs "Add music" **[code]**).

---

## 6. Failure modes (consolidated)

1. **Upload started, never finished** → `pending` TTL sweep (§3.9); object deleted if present.
2. **Direct PUT ok, finalize skipped** (tab closed) → same sweep; asset never became `ready`, so no clip can reference it (422 guard).
3. **Finalize validation fails** (magic bytes ≠ declared type, oversized, undecodable) → object deleted inline, `status='failed'`, client shown error.
4. **Content-Type mismatch on direct PUT** → R2 returns `403 SignatureDoesNotMatch` **[sourced]**; client retries with a fresh session.
5. **Two tabs edit the same clip** → clip `revision` conflict, 409 → existing `onConflict()` refetch flow **[code]**.
6. **Clip mutation during narration regen** → allowed (visual edits don't touch narration state); the remap/flagging at activation is the reconciliation point. Contrast: line edits during regen are blocked via `audio_status='generating'` **[code]** — clips need no such gate.
7. **Narration regenerated → overlays misaligned** → Phase 1: `needs_review` flags; Phase 2: deterministic remap + flags only for ambiguous cases (§3.6).
8. **User edits/deletes clips during export render** → job renders its materialized snapshot; result matches the project state at job creation (§3.8).
9. **Presigned GET expires mid-session** → refetch project mints fresh URLs (existing behavior for composition audio) **[code]**; canvas `Image.onerror` already degrades gracefully (skips drawing, logs) **[code]**.
10. **Asset delete while referenced** → FK RESTRICT + 409 with referencing clips (§3.9).
11. **Clip window beyond new (shorter) narration** → export truncates at audio duration anyway **[code]**; remap clamps + flags.
12. **Excessive overlay count** → validation caps guard filtergraph blowup (FFmpeg chained-overlay efficiency caveat **[sourced]**).
13. **Local dev** → `file://` URLs unusable in the browser **[code]** ⇒ proxy upload + HTTP serving route are required, not optional, for dev parity.

---

## 7. Unresolved product decisions

1. **Ripple policy end-state**: after narration regen, should aligned-looking clips silently remap (line-boundary algorithm, §3.6), always require user confirmation, or stay put? Recommendation is remap + flag ambiguity, but this changes user-visible behavior and needs a product call.
2. **Clips spanning the whole video vs. narration-bounded**: may a clip extend past the narration end (which would require extending video duration beyond `-t audio_duration`)? Currently impossible without pipeline changes.
3. **Asset library scope**: per-project (proposed MVP) vs per-user reuse across projects (affects `project_id` nullability, quota model, and GC).
4. **Supported media**: stills only (proposed), or GIF/short-video overlays in scope soon? (Different FFmpeg input handling and preview cost.)
5. **Z-order UX**: explicit z-index controls vs. "last added on top"; whether captions/characters must always stay above overlays (proposed: yes, captions on top — matches both current z stacks).
6. **Quotas**: max bytes per asset (10 MB proposed), per project, per user; max clips per project; max simultaneous overlaps.
7. **Overlay interaction with characters/captions**: any collision avoidance (the legacy preset system reserved zones for characters **[code]**), or full freeform with user responsibility (proposed)?
8. **Direct-upload rollout**: is proxy-only acceptable for launch (recommended), and if so what threshold (file size, traffic) triggers the presigned-PUT work + CORS configuration?

---

## 8. Sources

- OpenTimelineIO 0.18.1 — [Timeline Structure](https://opentimelineio.readthedocs.io/en/stable/tutorials/otio-timeline-structure.html) (Stack/Track/Clip/Gap, painter-order rendering, media_reference `target_url`/`available_range`); [Time Ranges](https://opentimelineio.readthedocs.io/en/stable/tutorials/time-ranges.html) (`source_range`, `range_in_parent`, sequential track invariant).
- FFmpeg Filters Documentation — [ffmpeg-filters.html](https://ffmpeg.org/ffmpeg-filters.html): `overlay` (§ overlay: inputs, x/y expression variables `W/H/w/h/t`, `eval=frame`, chaining caveat, `setpts` alignment note), Timeline editing (generic `enable` with `between(t,a,b)`), `scale` (`-n` aspect-preserving behavior), framesync options.
- Cloudflare R2 — [Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/): supported ops GET/HEAD/PUT/DELETE, POST unsupported, 1s–7d expiry, ContentType-in-signature → `403 SignatureDoesNotMatch`, CORS requirement, bearer-token guidance, custom-domain limitation.
- AWS S3 — [Uploading objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html) (PUT semantics, same-key replacement, 7-day max); [POST policy construction](https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-HTTPPOSTConstructPolicy.html) (`content-length-range` condition — POST-policy-only, hence unavailable on R2).
- This repository (commit state at time of writing): `backend/scripts/create_editor_tables.sql`, `backend/services/repositories/editor_repository.py`, `backend/services/editor_audio_service.py`, `backend/main.py`, `backend/storage/{base,r2_backend,local_backend,assets}.py`, `backend/services/video_service.py`, `backend/backend_pipeline/video_assembly/ffMpeg.py`, `backend/backend_pipeline/audio_generation/minimax_tts.py`, `frontend/lib/types.ts`, `frontend/lib/api.ts`, `frontend/lib/canvas-renderer/*`, `frontend/hooks/use-canvas-renderer.ts`, `frontend/components/create-video/{Editor,ImageOverlayEditor,EditorFooter,CanvasPreview}.tsx`.
