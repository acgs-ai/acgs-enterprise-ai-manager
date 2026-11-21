-- ACGS Enterprise Manager - Migration 002: recommendation persistence
-- Description: Let POST /recommendations/generate store engine output.
--   * entity_id becomes VARCHAR (API accepts arbitrary entity identifiers)
--   * status accepts the engine's 'approved' and 'pending_approval' values
--     (governance-blocked recommendations are never stored)
--   * adds metadata, governance_check and generated_at columns

BEGIN;

-- NOTE: changing the entity_id type takes an ACCESS EXCLUSIVE lock on
-- recommendations and rewrites the table (and rebuilds its indexes, including
-- idx_recommendations_entity on (entity_type, entity_id) from indexes.sql).
-- Run in a maintenance window on large tables.
ALTER TABLE recommendations
    ALTER COLUMN entity_id TYPE VARCHAR(255) USING entity_id::text;

-- Drop every CHECK constraint on recommendations that references status,
-- whatever its name (inline column checks get auto-generated names).
DO $$
DECLARE
    con RECORD;
BEGIN
    FOR con IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'recommendations'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ~ '\mstatus\M'
    LOOP
        EXECUTE format('ALTER TABLE recommendations DROP CONSTRAINT %I', con.conname);
    END LOOP;
END
$$;

ALTER TABLE recommendations
    ADD CONSTRAINT recommendations_status_check
    CHECK (status IN ('pending', 'accepted', 'rejected', 'implemented', 'approved', 'pending_approval'));

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS governance_check JSONB;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS generated_at TIMESTAMP WITH TIME ZONE;

COMMIT;
