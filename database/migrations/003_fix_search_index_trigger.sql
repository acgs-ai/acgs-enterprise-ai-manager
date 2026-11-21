-- ACGS Enterprise Manager - Migration 003: fix search index trigger
-- Description: update_search_index() read NEW.title, NEW.name, NEW.content and
--   NEW.tags directly. PL/pgSQL raises 'record "new" has no field ...' for any
--   column the table lacks (COALESCE does not help), so every INSERT/UPDATE on
--   tasks, projects, it_assets, infrastructure and documents failed. Read the
--   row through to_jsonb(NEW) instead, where a missing key is just NULL.
--   Same index contents as intended originally; no table changes.

BEGIN;

CREATE OR REPLACE FUNCTION update_search_index()
RETURNS TRIGGER AS $$
DECLARE
    row_data JSONB := to_jsonb(NEW);
    entry_title TEXT := COALESCE(row_data->>'title', row_data->>'name', '');
    entry_content TEXT := COALESCE(row_data->>'description', row_data->>'content', '');
BEGIN
    INSERT INTO search_index (entity_type, entity_id, domain, title, content, tags, search_vector)
    VALUES (
        TG_TABLE_NAME,
        NEW.id,
        CASE TG_TABLE_NAME
            WHEN 'tasks' THEN 'tasks'
            WHEN 'it_assets' THEN 'assets'
            WHEN 'infrastructure' THEN 'infrastructure'
            WHEN 'projects' THEN 'projects'
            WHEN 'financial_records' THEN 'financial'
            WHEN 'documents' THEN 'documents'
        END,
        entry_title,
        entry_content,
        CASE WHEN jsonb_typeof(row_data->'tags') = 'array'
             THEN row_data->'tags' ELSE '[]'::jsonb END,
        to_tsvector('english', entry_title || ' ' || entry_content)
    )
    ON CONFLICT (entity_type, entity_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        tags = EXCLUDED.tags,
        search_vector = EXCLUDED.search_vector,
        updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

COMMIT;
