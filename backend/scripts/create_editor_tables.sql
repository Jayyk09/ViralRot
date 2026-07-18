BEGIN;

CREATE TABLE IF NOT EXISTS editor_projects (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE,

    title TEXT NOT NULL
        CHECK (length(trim(title)) > 0),
    background_video_id TEXT,

    -- Optimistic concurrency for project-level edits such as line reordering.
    revision INTEGER NOT NULL DEFAULT 1
        CHECK (revision >= 1),

    -- Foreign key added after audio_compositions is created.
    active_composition_id UUID,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dialogue_lines (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES editor_projects(id)
        ON DELETE CASCADE,

    position INTEGER NOT NULL
        CHECK (position >= 0),
    caption TEXT NOT NULL
        CHECK (length(trim(caption)) > 0),
    speaker TEXT NOT NULL
        CHECK (length(trim(speaker)) > 0),
    emotion TEXT,

    -- Optimistic concurrency for edits to this line.
    revision INTEGER NOT NULL DEFAULT 1
        CHECK (revision >= 1),

    audio_status TEXT NOT NULL DEFAULT 'missing'
        CHECK (audio_status IN ('missing', 'generating', 'ready', 'stale', 'failed')),
    audio_error TEXT,

    -- Foreign key added after audio_segments is created.
    active_segment_id UUID,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_dialogue_lines_project_position
        UNIQUE (project_id, position)
        DEFERRABLE INITIALLY IMMEDIATE
);

-- Audio segment rows represent successfully uploaded, immutable artifacts.
CREATE TABLE IF NOT EXISTS audio_segments (
    id UUID PRIMARY KEY,
    line_id UUID NOT NULL
        REFERENCES dialogue_lines(id)
        ON DELETE CASCADE,

    storage_key TEXT NOT NULL UNIQUE,
    duration_ms INTEGER NOT NULL
        CHECK (duration_ms >= 0),
    voice_id TEXT NOT NULL
        CHECK (length(trim(voice_id)) > 0),

    -- Timings are relative to the beginning of this segment, in milliseconds.
    word_timings JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(word_timings) = 'array'),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audio_compositions (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES editor_projects(id)
        ON DELETE CASCADE,

    storage_key TEXT NOT NULL UNIQUE,
    duration_ms INTEGER NOT NULL
        CHECK (duration_ms >= 0),

    -- Ordered entries containing line_id, segment_id, start_ms, and end_ms.
    line_manifest JSONB NOT NULL
        CHECK (jsonb_typeof(line_manifest) = 'array'),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add the two active-artifact foreign keys after their target tables exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_dialogue_lines_active_segment'
    ) THEN
        ALTER TABLE dialogue_lines
            ADD CONSTRAINT fk_dialogue_lines_active_segment
            FOREIGN KEY (active_segment_id)
            REFERENCES audio_segments(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_editor_projects_active_composition'
    ) THEN
        ALTER TABLE editor_projects
            ADD CONSTRAINT fk_editor_projects_active_composition
            FOREIGN KEY (active_composition_id)
            REFERENCES audio_compositions(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_editor_projects_user_updated
    ON editor_projects(user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_dialogue_lines_project_position
    ON dialogue_lines(project_id, position);

CREATE INDEX IF NOT EXISTS idx_audio_segments_line_created
    ON audio_segments(line_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audio_compositions_project_created
    ON audio_compositions(project_id, created_at DESC);

COMMIT;
