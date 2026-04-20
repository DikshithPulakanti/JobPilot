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


def update_job_score(job_id: int, fit_score: float, recommendation: str) -> None:
    """Persist ``fit_score`` and ``recommendation`` for a job row."""
    sql = text(
        """
        UPDATE jobs
        SET fit_score = :fit_score, recommendation = :recommendation
        WHERE id = :job_id
        """
    )
    with connection() as conn:
        result = conn.execute(
            sql,
            {
                "job_id": int(job_id),
                "fit_score": float(fit_score),
                "recommendation": str(recommendation),
            },
        )
        if result.rowcount == 0:
            raise ValueError(f"No job found with id={job_id}")


def get_unscored_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """Jobs with ``fit_score`` NULL, newest by ``id`` first."""
    lim = max(1, min(int(limit), 500))
    sql = text(
        """
        SELECT id, title, company, url, description, source, found_at,
               fit_score, recommendation, location
        FROM jobs
        WHERE fit_score IS NULL
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


def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:
    """Return a single job row or ``None``."""
    sql = text(
        """
        SELECT id, title, company, url, description, source, found_at,
               fit_score, recommendation, location
        FROM jobs
        WHERE id = :jid
        """
    )
    with connection() as conn:
        row = conn.execute(sql, {"jid": int(job_id)}).mappings().first()
    if row is None:
        return None
    d = dict(row)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif k == "fit_score" and v is not None:
            d[k] = float(v)
    return d


def get_latest_candidate_profile() -> Optional[Dict[str, Any]]:
    """Most recent ``candidates`` row as a profile dict (JSONB lists decoded)."""
    sql = text(
        """
        SELECT name, email, phone, location, skills, experience_years, seniority,
               target_roles, education, visa_status, salary_min,
               preferred_locations, industries, summary
        FROM candidates
        ORDER BY id DESC
        LIMIT 1
        """
    )
    with connection() as conn:
        row = conn.execute(sql).mappings().first()
    if row is None:
        return None

    def _jsonish(val: Any) -> Any:
        if val is None:
            return []
        if isinstance(val, (list, dict)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return []
        return val

    d = dict(row)
    for key in ("skills", "target_roles", "education", "preferred_locations", "industries"):
        d[key] = _jsonish(d.get(key))

    ey = d.get("experience_years")
    if ey is not None:
        try:
            d["experience_years"] = int(round(float(ey)))
        except (TypeError, ValueError):
            d["experience_years"] = 0

    sm = d.get("salary_min")
    if sm is not None:
        try:
            d["salary_min"] = int(sm)
        except (TypeError, ValueError):
            d["salary_min"] = 0

    return d


def insert_application(
    job_id: int,
    status: str,
    cover_letter: str,
    form_filled: bool,
    error_message: Optional[str] = None,
) -> int:
    """Insert an application row and return its ``id``."""
    sql = text(
        """
        INSERT INTO applications (job_id, status, applied_at, cover_letter, form_filled, error_message)
        VALUES (:job_id, :status, NOW(), :cover_letter, :form_filled, :error_message)
        RETURNING id
        """
    )
    with connection() as conn:
        row = conn.execute(
            sql,
            {
                "job_id": int(job_id),
                "status": status,
                "cover_letter": cover_letter or "",
                "form_filled": bool(form_filled),
                "error_message": error_message,
            },
        ).fetchone()
        if row is None:
            raise RuntimeError("INSERT INTO applications did not return an id.")
        return int(row[0])


def get_candidate_by_id(candidate_id: int) -> Optional[Dict[str, Any]]:
    """Load one candidate row as the same profile shape as ``get_latest_candidate_profile``."""
    sql = text(
        """
        SELECT id, name, email, phone, location, skills, experience_years, seniority,
               target_roles, education, visa_status, salary_min,
               preferred_locations, industries, summary, preferences_text
        FROM candidates
        WHERE id = :cid
        """
    )
    with connection() as conn:
        row = conn.execute(sql, {"cid": int(candidate_id)}).mappings().first()
    if row is None:
        return None

    def _jsonish(val: Any) -> Any:
        if val is None:
            return []
        if isinstance(val, (list, dict)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return []
        return val

    d = dict(row)
    for key in ("skills", "target_roles", "education", "preferred_locations", "industries"):
        d[key] = _jsonish(d.get(key))

    ey = d.get("experience_years")
    if ey is not None:
        try:
            d["experience_years"] = int(round(float(ey)))
        except (TypeError, ValueError):
            d["experience_years"] = 0

    sm = d.get("salary_min")
    if sm is not None:
        try:
            d["salary_min"] = int(sm)
        except (TypeError, ValueError):
            d["salary_min"] = 0

    return d


def insert_event(
    action: str,
    company: Optional[str] = None,
    title: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
) -> int:
    """Persist a pipeline / dashboard event to ``events``."""
    sql = text(
        """
        INSERT INTO events (action, company, title, details, status)
        VALUES (:action, :company, :title, CAST(:details AS jsonb), :status)
        RETURNING id
        """
    )
    payload = {
        "action": str(action),
        "company": company,
        "title": title,
        "details": json.dumps(details if details is not None else {}),
        "status": status,
    }
    with connection() as conn:
        row = conn.execute(sql, payload).fetchone()
        if row is None:
            raise RuntimeError("INSERT INTO events did not return an id.")
        return int(row[0])
