-- ACGS Enterprise Manager - Migration 002: recommendation persistence
-- Description: Let POST /recommendations/generate store engine output.
--   * entity_id becomes VARCHAR (API accepts arbitrary entity identifiers)
--   * status accepts the engine's 'approved' and 'pending_approval' values
--     (governance-blocked recommendations are never stored)
--   * adds metadata, governance_check and generated_at columns

BEGIN;

ALTER TABLE recommendations
    ALTER COLUMN entity_id TYPE VARCHAR(255) USING entity_id::text;

ALTER TABLE recommendations DROP CONSTRAINT IF EXISTS recommendations_status_check;
ALTER TABLE recommendations
    ADD CONSTRAINT recommendations_status_check
    CHECK (status IN ('pending', 'accepted', 'rejected', 'implemented', 'approved', 'pending_approval'));

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS governance_check JSONB;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS generated_at TIMESTAMP WITH TIME ZONE;

COMMIT;
