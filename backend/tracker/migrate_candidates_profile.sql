-- Add profile-builder columns to an existing `candidates` table (safe to re-run).
--
-- Option A (loads .env for you — recommended):
--   cd backend && python tracker/apply_profile_columns_migration.py
--
-- Option B (shell must have DATABASE_URL exported):
--   psql "$DATABASE_URL" -f tracker/migrate_candidates_profile.sql

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT '';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS education JSONB DEFAULT '[]'::jsonb;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS preferred_locations JSONB DEFAULT '[]'::jsonb;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS industries JSONB DEFAULT '[]'::jsonb;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS preferences_text TEXT;
