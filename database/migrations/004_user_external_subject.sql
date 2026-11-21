-- ACGS Enterprise Manager - Migration 004: users.external_subject
-- Description: Financial approve/reject resolve the approver as the active
--   user whose external_subject equals the verified token's `sub` (an opaque
--   IdP subject, not necessarily a UUID). users.id is no longer assumed to
--   equal `sub`.
--   * adds nullable external_subject TEXT with a unique index
--   * no backfill: the IdP-subject-to-user mapping cannot be derived from
--     existing data. An administrator must populate external_subject for each
--     existing user before that user can approve or reject; until then the
--     API answers 403 "Approver identity not provisioned".
--   Idempotent: safe to run more than once.

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS external_subject TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_external_subject
    ON users(external_subject);

COMMIT;
