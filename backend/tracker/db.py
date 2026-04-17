"""PostgreSQL helpers using SQLAlchemy (sync) and DATABASE_URL."""

import json
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

_engine: Optional[Engine] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set.")
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


@contextmanager
def connection() -> Generator[Any, None, None]:
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def healthcheck() -> bool:
    try:
        with connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def insert_candidate_profile(profile: Dict[str, Any], preferences: str = "") -> int:
    """
    Insert a structured candidate profile (from ``build_candidate_profile``) and return ``id``.
    """
    if profile.get("error"):
        raise ValueError("Cannot insert profile with error payload")

    sql = text(
        """
        INSERT INTO candidates (
            name, email, phone, location, skills, experience_years, seniority,
            target_roles, education, visa_status, salary_min,
            preferred_locations, industries, summary, preferences_text
        ) VALUES (
            :name, :email, :phone, :location,
            CAST(:skills AS jsonb), :experience_years, :seniority,
            CAST(:target_roles AS jsonb), CAST(:education AS jsonb), :visa_status, :salary_min,
            CAST(:preferred_locations AS jsonb), CAST(:industries AS jsonb), :summary, :preferences_text
        )
        RETURNING id
        """
    )

    params = {
        "name": profile["name"],
        "email": profile["email"],
        "phone": profile.get("phone") or "",
        "location": profile.get("location") or "",
        "skills": json.dumps(profile.get("skills", [])),
        "experience_years": int(profile.get("experience_years", 0)),
        "seniority": profile.get("seniority"),
        "target_roles": json.dumps(profile.get("target_roles", [])),
        "education": json.dumps(profile.get("education", [])),
        "visa_status": profile.get("visa_status"),
        "salary_min": int(profile.get("salary_min", 0)),
        "preferred_locations": json.dumps(profile.get("preferred_locations", [])),
        "industries": json.dumps(profile.get("industries", [])),
        "summary": profile.get("summary") or "",
        "preferences_text": preferences or "",
    }

    try:
        with connection() as conn:
            result = conn.execute(sql, params)
            row = result.fetchone()
            if row is None:
                raise RuntimeError("INSERT INTO candidates did not return an id.")
            return int(row[0])
    except RuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001
        orig = getattr(exc, "orig", None)
        if orig is not None and type(orig).__name__ == "UndefinedColumn":
            raise RuntimeError(
                "Candidates table is missing profile columns. From the `backend` directory run:\n"
                "  python tracker/apply_profile_columns_migration.py\n"
                "or (after exporting DATABASE_URL):\n"
                '  psql "$DATABASE_URL" -f tracker/migrate_candidates_profile.sql\n'
                "Then retry POST /start."
            ) from exc
        raise RuntimeError(f"Database error while saving candidate: {exc!s}") from exc


def save_job(job: Dict[str, Any]) -> int:
    """
    Insert a job row and return its ``id``.

    Expected keys: title, company, url, description (optional), source (optional),
    location (optional).
    """
    sql = text(
        """
        INSERT INTO jobs (
            title, company, url, description, source, found_at, location
        ) VALUES (
            :title, :company, :url, :description, :source, NOW(), :location
        )
        RETURNING id
        """
    )
    params = {
        "title": str(job.get("title", "")).strip() or "Untitled",
        "company": str(job.get("company", "")).strip() or "Unknown",
        "url": str(job.get("url", "")).strip(),
        "description": (job.get("description") or None),
        "source": str(job.get("source") or "indeed"),
        "location": str(job.get("location") or ""),
    }
    if not params["url"]:
        raise ValueError("job.url is required for save_job")

    try:
        with connection() as conn:
            existing = conn.execute(
                text("SELECT id FROM jobs WHERE url = :url"),
                {"url": params["url"]},
            ).fetchone()
            if existing is not None:
                return int(existing[0])
            result = conn.execute(sql, params)
            row = result.fetchone()
            if row is None:
                raise RuntimeError("INSERT INTO jobs did not return an id.")
            return int(row[0])
    except Exception as exc:  # noqa: BLE001
        orig = getattr(exc, "orig", None)
        if orig is not None and type(orig).__name__ == "UndefinedColumn":
            raise RuntimeError(
                'Jobs table is missing the "location" column. From `backend` run:\n'
                '  psql "$DATABASE_URL" -c "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT \'\'"\n'
                "or re-run tracker/schema.sql against your database."
            ) from exc
        raise RuntimeError(f"Database error while saving job: {exc!s}") from exc


def get_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent jobs (newest ``id`` first) as plain dicts."""
    lim = max(1, min(int(limit), 500))
    sql = text(
        """
        SELECT id, title, company, url, description, source, found_at,
               fit_score, recommendation, location
        FROM jobs
        ORDER BY id DESC
        LIMIT :lim
        """
    )
    with connection() as conn:
        rows = conn.execute(sql, {"lim": lim}).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
            elif k == "fit_score" and v is not None:
                d[k] = float(v)
        out.append(d)
    return out
