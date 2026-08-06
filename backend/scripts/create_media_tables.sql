-- Timeline-native image overlays: project-scoped media assets (file identity)
-- and timeline clips (placement). Clips are never attached to dialogue lines.
-- Safe to rerun (idempotent, mirrors create_editor_tables.sql conventions).

BEGIN;

-- One row per successfully normalized + uploaded image. Rows are only
-- inserted after the WebP normalization and storage upload succeed, so
-- every persisted asset is immediately usable ('ready').
CREATE TABLE IF NOT EXISTS media_assets (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,
    project_id UUID NOT NULL
        REFERENCES editor_projects(id)
        ON DELETE CASCADE,

    kind TEXT NOT NULL DEFAULT 'image'
        CHECK (kind IN ('image')),          -- future: 'video', 'audio'

    -- Server-generated key; the client filename is display metadata only.
    storage_key TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,

    -- Uploads are normalized to WebP; source PNG/JPEG/WebP is not retained.
    content_type TEXT NOT NULL
        CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),

    -- Validated server-side from the normalized bytes, never trusted from
    -- the client.
    byte_size BIGINT NOT NULL
        CHECK (byte_size > 0),
    width_px INTEGER NOT NULL
        CHECK (width_px > 0 AND width_px <= 4096),
    height_px INTEGER NOT NULL
        CHECK (height_px > 0 AND height_px <= 4096),

    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_media_assets_project_created
    ON media_assets(project_id, created_at);

-- One row per placement of an asset on the project timeline. Many clips may
-- reference one asset (reuse without re-upload).
CREATE TABLE IF NOT EXISTS timeline_clips (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES editor_projects(id)
        ON DELETE CASCADE,

    -- RESTRICT: an asset referenced by any clip cannot be hard-deleted.
    asset_id UUID NOT NULL
        REFERENCES media_assets(id)
        ON DELETE RESTRICT,

    -- Absolute time on the active composition timeline, in milliseconds
    -- (same unit as audio_compositions.line_manifest).
    start_ms INTEGER NOT NULL
        CHECK (start_ms >= 0),
    end_ms INTEGER NOT NULL,
    CONSTRAINT ck_timeline_clips_range CHECK (end_ms > start_ms),

    -- Normalized geometry as fractions of the output frame, top-left anchor.
    -- Height derives from the asset's intrinsic aspect ratio.
    x DOUBLE PRECISION NOT NULL
        CHECK (x >= 0 AND x <= 1),
    y DOUBLE PRECISION NOT NULL
        CHECK (y >= 0 AND y <= 1),
    width DOUBLE PRECISION NOT NULL
        CHECK (width > 0 AND width <= 1),
    z_index INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT ck_timeline_clips_z_index
        CHECK (z_index >= -1000 AND z_index <= 1000),

    -- Which narration timeline the times were authored against. Composition
    -- activation clamps clip ends to the new duration and flags clips that
    -- start beyond it as 'needs_review' (never deletes them).
    authored_composition_id UUID
        REFERENCES audio_compositions(id)
        ON DELETE SET NULL,
    timing_status TEXT NOT NULL DEFAULT 'aligned'
        CHECK (timing_status IN ('aligned', 'needs_review')),

    -- Manual clips are user-created or have been edited by the user.
    -- Generated clips may be replaced by a later visual-generation run.
    origin TEXT NOT NULL DEFAULT 'manual',
    CONSTRAINT ck_timeline_clips_origin
        CHECK (origin IN ('manual', 'generated')),

    -- Optimistic concurrency for autosaved geometry/time edits (mirrors
    -- dialogue_lines.revision).
    revision INTEGER NOT NULL DEFAULT 1
        CHECK (revision >= 1),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Upgrade databases created before clip origin was introduced. Adding the
-- nullable column first makes the explicit backfill clear, while the final
-- default ensures clips created by origin-unaware code remain manual.
ALTER TABLE timeline_clips
    ADD COLUMN IF NOT EXISTS origin TEXT;

UPDATE timeline_clips
SET origin = 'manual'
WHERE origin IS NULL;

ALTER TABLE timeline_clips
    ALTER COLUMN origin SET DEFAULT 'manual',
    ALTER COLUMN origin SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_timeline_clips_origin'
          AND conrelid = 'timeline_clips'::regclass
    ) THEN
        ALTER TABLE timeline_clips
            ADD CONSTRAINT ck_timeline_clips_origin
            CHECK (origin IN ('manual', 'generated'));
    END IF;
END
$$;

-- Add the bound when upgrading a database where timeline_clips already
-- existed before this migration learned about z-index limits.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_timeline_clips_z_index'
          AND conrelid = 'timeline_clips'::regclass
    ) THEN
        ALTER TABLE timeline_clips
            ADD CONSTRAINT ck_timeline_clips_z_index
            CHECK (z_index >= -1000 AND z_index <= 1000);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_timeline_clips_project_start
    ON timeline_clips(project_id, start_ms);

CREATE INDEX IF NOT EXISTS idx_timeline_clips_asset
    ON timeline_clips(asset_id);

CREATE INDEX IF NOT EXISTS idx_timeline_clips_project_origin
    ON timeline_clips(project_id, origin);

COMMIT;
