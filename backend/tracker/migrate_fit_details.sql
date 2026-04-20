-- Persist LLM fit rationale (per-dimension reasons, summary, red flags). Safe to re-run.
-- Usage: psql "$DATABASE_URL" -f tracker/migrate_fit_details.sql

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fit_details JSONB;
