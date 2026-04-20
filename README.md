# JobPilot

Autonomous job application agent: turn resume text and preferences into discovered jobs, scored matches, and browser-assisted application drafts—using **Playwright (computer use)** and **GPT‑4o Vision** to read real application UIs.

## What It Does

JobPilot ingests plain-text resume and job preferences, builds a structured candidate profile, searches job boards (Indeed via Playwright), scores each role with Claude, then opens apply flows in a real browser. It uses vision-first form understanding with DOM fallback, fills fields from your profile, generates a tailored cover letter per role, and persists jobs, applications, and live events to PostgreSQL. The main technical bet is **computer use + multimodal vision** so one stack can handle heterogeneous ATS pages instead of one-off parsers.

## System Architecture

Orchestration is a **LangGraph** `StateGraph` defined in `backend/orchestrator/graph.py`. Nodes (exact names):

| Node | Role |
|------|------|
| `load_candidate` | Load candidate profile from inline state, `candidate_id`, or latest DB row; publish pipeline start metadata. |
| `job_search` | Run Indeed discovery (`agents/job_finder`); wrapped with retry/backoff. |
| `scoring` | Score each discovered job (`agents/fit_scorer`); wrapped with retry/backoff. |
| `applications` | Optionally run browser apply flows for top apply/review jobs; wrapped with retry/backoff. |
| `finalize` | Emit completion (and errors / `failed_nodes` when present). |

**Edges**

- Entry → `load_candidate`.
- **Conditional after `load_candidate`:** `_route_after_load_candidate` routes to `job_search` if the profile is valid (non-empty name, non-empty `skills` list, and either `candidate_id` in state or `id` on the profile); otherwise **`END`** (invalid profile, aborted load, or missing identity).
- **Conditional after `job_search`:** `_route_after_job_search` routes to **`finalize`** if `jobs_found` is empty; otherwise to **`scoring`**.
- `scoring` → `applications` → `finalize` → **`END`**.

Transient failures in `job_search`, `scoring`, and `applications` are retried (see `retry_with_backoff` in the same file); exhausted retries record `pipeline_error` events and append to `failed_nodes` without aborting the whole graph when possible.

## Agents

Eight primary agent modules (single-responsibility units under `backend/agents/`):

| # | Module | Responsibility |
|---|--------|----------------|
| 1 | `profile_builder.py` | Extract structured candidate fields from raw resume + preferences (Claude). |
| 2 | `job_finder.py` | Playwright-based Indeed job discovery and persistence. |
| 3 | `fit_scorer.py` | Multi-dimensional job fit scoring and apply/review/skip recommendation (Claude). |
| 4 | `scorer_runner.py` | CLI/script to batch-score unscored jobs in PostgreSQL using `fit_scorer`. |
| 5 | `form_reader.py` | GPT‑4o Vision (+ DOM fallback) to enumerate application form fields on a page. |
| 6 | `form_filler.py` | Map profile + cover letter into fields via Playwright. |
| 7 | `cover_letter.py` | Generate a tailored cover letter per job (Claude). |
| 8 | `apply_navigator.py` | Dismiss overlays, click Apply, handle Indeed auth-wall detection and external ATS navigation. |

**Related modules:** `application_runner.py` wires cover letter → Playwright → read/fill for a single `job_id`; `captcha_handler.py` and `follow_up.py` support optional flows not central to the default LangGraph path.

## Tech Stack

| Backend (`backend/requirements.txt`) | Frontend (`frontend/package.json`) |
|--------------------------------------|-------------------------------------|
| Python: FastAPI, Uvicorn | Next.js 14, React 18 |
| LangGraph, langchain-core, langchain-anthropic | Tailwind CSS, PostCSS, Autoprefixer |
| Anthropic & OpenAI SDKs, httpx | Recharts |
| Playwright | TypeScript |
| PostgreSQL drivers: psycopg2-binary, SQLAlchemy, Alembic, asyncpg |  |
| SSE: sse-starlette |  |
| Utilities: python-dotenv, Pydantic, BeautifulSoup, requests, aiohttp |  |
| OCR / captcha-related: pytesseract, Pillow, twocaptcha |  |

## API Reference

All routes are mounted at the app root (no `/api` prefix). Definitions: `backend/api/routes.py`, `backend/api/events.py`, `backend/main.py`.

### `GET /health`

**Response:** `{ "status": "ok" }`

### `GET /health/db`

**Response:** `{ "status": "ok" | "error", "database": "connected" | "unavailable" }`

### `POST /start`

**Body (`StartRequest`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `resume_text` | `string` | yes | Raw resume text |
| `preferences` | `string` | no (default `""`) | Free-form job preferences |
| `run_pipeline` | `boolean` | no (default `false`) | If `true`, run `run_full_pipeline` in a background task after saving the candidate |

**Success response:** `{ "id": <int>, ...profile fields... }` — the saved candidate id plus the structured profile dict returned by `build_candidate_profile`.  
If `run_pipeline` is true, also: `"pipeline": "started"`.

**Errors:** `400` if `resume_text` is empty; `502` if profile build returns an error string; `503`/`500` for database failures.

### `POST /run-pipeline`

**Body (`PipelineRequest`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `candidate_id` | `int \| null` | no | Candidate id; `null`/omitted uses latest saved profile per pipeline implementation |

**Response:** `{ "status": "started", "candidate_id": <int or null> }`  
Runs `run_full_pipeline` in a background task; events stream on `GET /events` and are persisted when publishing succeeds.

### `GET /metrics`

**Response:** JSON object from `get_dashboard_metrics()`, e.g. integer counts: `jobs_total`, `jobs_scored`, `applications_total`, `rec_apply`, `rec_review`, `rec_skip`.

### `GET /stats/recommendations`

**Response:** `{ "<recommendation>": <int>, ... }` — counts per job recommendation bucket from the database.

### `GET /stats/fit-histogram`

**Response:** `list[{ "bucket_label": str, "count": int }, ...]` — histogram buckets for scored jobs.

### `GET /applications`

**Query:** `limit` (int, default `100`, capped in DB layer).

**Response:** List of application rows joined to job fields (`application_id`, `job_id`, `status`, `applied_at`, `form_filled`, `error_message`, `title`, `company`, `fit_score`, `recommendation`, `url`, …).

### `GET /jobs`

**Query:** `limit` (int, default `50`).

**Response:** List of recent job dicts (`id`, `title`, `company`, `url`, `description`, `source`, `found_at`, `fit_score`, `recommendation`, `location`).

## SSE Events

`GET /events` returns **Server-Sent Events** (`EventSourceResponse`). Each pushed event uses the SSE event name **`jobpilot`**, and the **data** payload is a JSON string of an object with:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `string` (ISO 8601 UTC) | Added in `EventHub.publish` before broadcast |
| `action` | `string` | e.g. `pipeline_started`, `jobs_found`, `jobs_scored`, `application_filled`, `pipeline_completed`, `pipeline_error`, `stream_connected`, … |
| `company` | `string \| null` | Optional company context |
| `title` | `string \| null` | Optional job title context |
| `details` | `object` | Structured details (varies by `action`) |
| `status` | `string \| null` | e.g. `info`, `success`, `error` |

The stream also emits periodic **`ping`** events with empty JSON to keep connections alive. On connect, a `stream_connected` event is published with `status: "info"`.

## Database Schema

Source: `backend/tracker/schema.sql` (PostgreSQL). `events.details` is stored as **JSONB**.

### `candidates`

`id`, `name`, `email`, `phone`, `location`, `skills` (JSONB), `experience_years`, `seniority`, `target_roles` (JSONB), `education` (JSONB), `visa_status`, `salary_min`, `preferred_locations` (JSONB), `industries` (JSONB), `summary`, `preferences_text`, `created_at`.

### `jobs`

`id`, `title`, `company`, `url`, `description`, `source`, `found_at`, `fit_score`, `recommendation`, `location`.

### `applications`

`id`, `job_id` (FK → `jobs.id`), `status` (text; default **`pending`** — application code also uses values such as **`filled`**, **`auth_blocked`**, etc.), `applied_at`, `cover_letter`, `form_filled`, `error_message`.

### `events`

`id`, `timestamp`, `action`, `company`, `title`, `details` (JSONB), `status`.

## Setup & Running

1. **Prerequisites:** Python **3.11+**, Node **18+**, PostgreSQL **15+**, **Anthropic** and **OpenAI** API keys, **Git**. Optional: `psql` CLI for DB setup; for Terraform, AWS CLI and Terraform.

2. **Clone and Python env**
   ```bash
   git clone https://github.com/DikshithPulakanti/JobPilot.git
   cd JobPilot/backend
   python3.11 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m playwright install chromium
   ```

3. **Database**
   ```bash
   createdb jobpilot
   psql jobpilot -f tracker/schema.sql
   ```

4. **Environment** — copy `backend/.env.example` to `backend/.env` and fill values (see table below).

5. **Backend**
   ```bash
   cd backend && source venv/bin/activate
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

6. **Frontend**
   ```bash
   cd frontend && npm install && npm run dev
   ```
   Default UI: `http://localhost:3000` (CORS allows this origin against the API).

7. **CLI pipeline** (builds profile from `backend/resume.txt`, inserts candidate, runs `run_full_pipeline` with a no-op publisher):
   ```bash
   cd backend && source venv/bin/activate
   python -m orchestrator.graph
   ```

8. **Trigger pipeline via API**
   ```bash
   curl -s -X POST http://127.0.0.1:8000/run-pipeline \
     -H "Content-Type: application/json" \
     -d '{"candidate_id": 1}'
   ```

## Environment Variables

From `backend/.env.example`:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** (for Claude features) | Anthropic API key for profile, scoring, cover letters. |
| `OPENAI_API_KEY` | **Yes** (for vision form reading) | OpenAI API key for GPT‑4o Vision in `form_reader`. |
| `DATABASE_URL` | **Yes** (for persistence) | PostgreSQL connection string (e.g. `postgresql://localhost:5432/jobpilot`). |
| `PLAYWRIGHT_HEADLESS` | Optional | If set (e.g. `true`), headless browser for job finder / apply flows. |
| `JOBPILOT_MAX_APPLICATIONS_PER_RUN` | Optional | Max apply/review jobs to process per pipeline run (default **`0`** skips browser applications). |
| `GITHUB_TOKEN` | Optional | Used where repository automation expects GitHub access. |
| `TWOCAPTCHA_API_KEY` | Optional | 2Captcha integration when captcha flows are enabled. |
| `LINKEDIN_EMAIL` | Optional | LinkedIn-related automation when used. |
| `LINKEDIN_PASSWORD` | Optional | LinkedIn-related automation when used. |

Additional variables may be read in code (e.g. `ANTHROPIC_MODEL` defaults in agents) but are not listed in `.env.example`.

## Deployment

Infrastructure-as-code lives under **`terraform/`**. Modules:

1. **`modules/secrets`** — SSM SecureString parameters, IAM role for EC2 (SSM + logs), instance profile.  
2. **`modules/networking`** — VPC, public/private subnets, NAT, security groups.  
3. **`modules/database`** — RDS PostgreSQL, subnet group; **`null_resource`** with **`local-exec`** applies `backend/tracker/schema.sql` via `psql` from the machine running **`terraform apply`** (requires AWS credentials, `psql`, and network path to RDS; adjust SG/VPN/bastion as needed).  
4. **`modules/backend`** — EC2, Elastic IP, user-data bootstrap.  
5. **`modules/frontend`** — S3 bucket (assets) and CloudFront distribution.

Populate **SSM parameters** (`/jobpilot/*`) with real secrets before `terraform apply`. The bundled user-data expects those values and clones the app repo per your template.

## Project Status

Core LangGraph pipeline, API, dashboard, and Terraform layout are in place; **end-to-end submission** to every employer ATS is limited by **external auth walls**, site-specific flows, and legal/ToS constraints—browser automation fills forms but does not guarantee unattended submit on all sites.
