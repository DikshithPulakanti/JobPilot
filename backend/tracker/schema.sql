-- JobPilot database schema (PostgreSQL)
--
-- Upgrading an older database? Run once:
--   psql "$DATABASE_URL" -f tracker/migrate_candidates_profile.sql

CREATE TABLE IF NOT EXISTS candidates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    skills JSONB DEFAULT '[]'::jsonb,
    experience_years INTEGER,
    seniority TEXT,
    target_roles JSONB DEFAULT '[]'::jsonb,
    education JSONB DEFAULT '[]'::jsonb,
    visa_status TEXT,
    salary_min INTEGER,
    preferred_locations JSONB DEFAULT '[]'::jsonb,
    industries JSONB DEFAULT '[]'::jsonb,
    summary TEXT NOT NULL DEFAULT '',
    preferences_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotent upgrades for databases created with an older schema.sql
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT '';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS education JSONB DEFAULT '[]'::jsonb;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS preferred_locations JSONB DEFAULT '[]'::jsonb;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS industries JSONB DEFAULT '[]'::jsonb;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS preferences_text TEXT;

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    source TEXT,
    found_at TIMESTAMPTZ,
    fit_score NUMERIC(5, 2),
    recommendation TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    applied_at TIMESTAMPTZ,
    cover_letter TEXT,
    form_filled BOOLEAN DEFAULT FALSE,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action TEXT NOT NULL,
    company TEXT,
    title TEXT,
    details JSONB,
    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
