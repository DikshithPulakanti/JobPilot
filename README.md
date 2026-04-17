# JobPilot

JobPilot is a monorepo scaffold for an AI-assisted job search and application workflow: a FastAPI backend with LangGraph orchestration, Playwright-ready agents, PostgreSQL tracking, and a Next.js dashboard with a live SSE feed.

## Layout

- `backend/` — FastAPI app, agents, orchestrator, tracker, and API modules.
- `frontend/` — Next.js 14 (App Router) dashboard with Tailwind CSS.

Copy `backend/.env.example` to `backend/.env` and fill in API keys and database credentials before running services.

## Backend quick start

If `source venv/bin/activate` reports “no such file or directory”, create the environment first (`python3 -m venv venv` in `backend/`), then `pip install -r requirements.txt`. Run `uvicorn` only with that venv activated (or use `venv/bin/uvicorn` directly); otherwise you may see missing modules such as `sse_starlette` from your global or conda base install.

From the `backend` directory (see exact commands in the setup section below):

1. Create and activate a Python virtual environment named `venv`.
2. Install Python dependencies from `requirements.txt`.
3. Install Playwright browsers.
4. Create the PostgreSQL database `jobpilot` and apply `tracker/schema.sql`.
5. Start Uvicorn on `http://127.0.0.1:8000`.

## Frontend quick start

```bash
cd frontend
npm install
npm run dev
```

The dashboard defaults to `http://localhost:3000` and expects the API at `http://localhost:8000` (override with `NEXT_PUBLIC_API_URL` if needed).

## API surface

- `GET /health` — `{"status": "ok"}`.
- `GET /health/db` — lightweight database connectivity check (optional helper).
- `POST /start` — accepts a candidate profile JSON body and starts the LangGraph orchestrator in the background.
- `GET /events` — Server-Sent Events stream for dashboard updates.
