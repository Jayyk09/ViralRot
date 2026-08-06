-- Add manual/generated origin tracking to persisted timeline clips.
-- Safe to rerun: existing generated values are preserved, while clips that
-- predate this column are backfilled as manual.

BEGIN;

-- Fail rather than waiting indefinitely behind application traffic. The
-- transaction-scoped advisory lock also prevents two copies of this migration
-- from racing through the constraint existence check.
SET LOCAL lock_timeout = '5s';

DO $migration_lock$
BEGIN
    IF NOT pg_try_advisory_xact_lock(
        hashtextextended('viratrot:migrate_timeline_clip_origin', 0)
    ) THEN
        RAISE EXCEPTION 'timeline clip origin migration is already running'
            USING ERRCODE = '55P03';
    END IF;
END
$migration_lock$;

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

-- This intentionally is not CONCURRENTLY: CREATE INDEX CONCURRENTLY cannot run
-- in this migration's transaction. The lock timeout keeps a busy database from
-- waiting indefinitely; large production tables should add this index
-- concurrently as a separately orchestrated deployment step.
CREATE INDEX IF NOT EXISTS idx_timeline_clips_project_origin
    ON timeline_clips(project_id, origin);

COMMIT;
