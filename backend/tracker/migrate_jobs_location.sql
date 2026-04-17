-- Add job listing location column (safe to re-run).
-- Usage: psql "$DATABASE_URL" -f tracker/migrate_jobs_location.sql

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT '';
