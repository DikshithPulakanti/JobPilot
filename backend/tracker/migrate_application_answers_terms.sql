-- One-time application answers (EEO / visa detail) and best-effort terms text from apply iframes.
-- Usage: psql "$DATABASE_URL" -f tracker/migrate_application_answers_terms.sql

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS application_answers JSONB DEFAULT '{}'::jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS terms_snippet TEXT;
