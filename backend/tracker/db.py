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


def _application_answers_dict(val: Any) -> Dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, str):
        try:
            o = json.loads(val)
        except json.JSONDecodeError:
            return {}
        return dict(o) if isinstance(o, dict) else {}
    return {}


def _parse_fit_details(val: Any) -> Optional[Dict[str, Any]]:
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalize_job_row(d: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif k == "fit_score" and v is not None:
            d[k] = float(v)
        elif k == "fit_details":
            d[k] = _parse_fit_details(v)
    return d


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
            preferred_locations, industries, summary, preferences_text,
            application_answers
        ) VALUES (
            :name, :email, :phone, :location,
            CAST(:skills AS jsonb), :experience_years, :seniority,
            CAST(:target_roles AS jsonb), CAST(:education AS jsonb), :visa_status, :salary_min,
            CAST(:preferred_locations AS jsonb), CAST(:industries AS jsonb), :summary, :preferences_text,
            CAST(:application_answers AS jsonb)
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
        "application_answers": json.dumps(profile.get("application_answers") or {}),
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
               fit_score, recommendation, location, fit_details, terms_snippet
        FROM jobs
        ORDER BY id DESC
        LIMIT :lim
        """
    )
    with connection() as conn:
        rows = conn.execute(sql, {"lim": lim}).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(_normalize_job_row(dict(r)))
    return out


def update_job_score(
    job_id: int,
    fit_score: float,
    recommendation: str,
    *,
    fit_details: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist ``fit_score``, ``recommendation``, and optional structured fit rationale."""
    if fit_details is not None:
        sql = text(
            """
            UPDATE jobs
            SET fit_score = :fit_score,
                recommendation = :recommendation,
                fit_details = CAST(:fit_details AS jsonb)
            WHERE id = :job_id
            """
        )
        params: Dict[str, Any] = {
            "job_id": int(job_id),
            "fit_score": float(fit_score),
            "recommendation": str(recommendation),
            "fit_details": json.dumps(fit_details),
        }
    else:
        sql = text(
            """
            UPDATE jobs
            SET fit_score = :fit_score, recommendation = :recommendation
            WHERE id = :job_id
            """
        )
        params = {
            "job_id": int(job_id),
            "fit_score": float(fit_score),
            "recommendation": str(recommendation),
        }
    try:
        with connection() as conn:
            result = conn.execute(sql, params)
        if result.rowcount == 0:
            raise ValueError(f"No job found with id={job_id}")
    except Exception as exc:  # noqa: BLE001
        orig = getattr(exc, "orig", None)
        if (
            fit_details is not None
            and orig is not None
            and type(orig).__name__ == "UndefinedColumn"
        ):
            raise RuntimeError(
                'Jobs table is missing the "fit_details" column. From the `backend` directory run:\n'
                '  psql "$DATABASE_URL" -f tracker/migrate_fit_details.sql\n'
                "or apply tracker/schema.sql to your database."
            ) from exc
        raise


def update_job_terms_snippet(job_id: int, terms_snippet: str) -> None:
    """Best-effort legal / terms text observed on the application flow (may be empty)."""
    sql = text(
        """
        UPDATE jobs
        SET terms_snippet = :terms_snippet
        WHERE id = :job_id
        """
    )
    with connection() as conn:
        conn.execute(
            sql,
            {
                "job_id": int(job_id),
                "terms_snippet": (terms_snippet or "")[:24000] or None,
            },
        )


def get_unscored_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """Jobs with ``fit_score`` NULL, newest by ``id`` first."""
    lim = max(1, min(int(limit), 500))
    sql = text(
        """
        SELECT id, title, company, url, description, source, found_at,
               fit_score, recommendation, location, fit_details, terms_snippet
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
        out.append(_normalize_job_row(dict(r)))
    return out


def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:
    """Return a single job row or ``None``."""
    sql = text(
        """
        SELECT id, title, company, url, description, source, found_at,
               fit_score, recommendation, location, fit_details, terms_snippet
        FROM jobs
        WHERE id = :jid
        """
    )
    with connection() as conn:
        row = conn.execute(sql, {"jid": int(job_id)}).mappings().first()
    if row is None:
        return None
    return _normalize_job_row(dict(row))


def get_latest_candidate_profile() -> Optional[Dict[str, Any]]:
    """Most recent ``candidates`` row as a profile dict (JSONB lists decoded)."""
    sql = text(
        """
        SELECT id, name, email, phone, location, skills, experience_years, seniority,
               target_roles, education, visa_status, salary_min,
               preferred_locations, industries, summary, preferences_text,
               application_answers
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

    d["application_answers"] = _application_answers_dict(d.get("application_answers"))

    return d


def merge_latest_candidate_application_answers(patch: Dict[str, Any]) -> int:
    """
    Merge ``patch`` into the latest candidate's ``application_answers`` JSON (shallow merge).
    Returns the candidate ``id``.
    """
    latest = get_latest_candidate_profile()
    if not latest or not latest.get("id"):
        raise ValueError("No candidate profile exists. Run POST /start first.")
    cid = int(latest["id"])
    base = _application_answers_dict(latest.get("application_answers"))
    merged = {**base, **(patch or {})}
    sql = text(
        """
        UPDATE candidates
        SET application_answers = CAST(:application_answers AS jsonb)
        WHERE id = :id
        """
    )
    with connection() as conn:
        result = conn.execute(
            sql,
            {"id": cid, "application_answers": json.dumps(merged)},
        )
        if result.rowcount == 0:
            raise ValueError(f"No candidate with id={cid}")
    return cid


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
               preferred_locations, industries, summary, preferences_text,
               application_answers
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

    d["application_answers"] = _application_answers_dict(d.get("application_answers"))

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


def get_dashboard_metrics() -> Dict[str, Any]:
    """Aggregate counts for the dashboard (jobs, scored, applications, recommendations)."""
    sql = text(
        """
        SELECT
            (SELECT COUNT(*) FROM jobs) AS jobs_total,
            (SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL) AS jobs_scored,
            (SELECT COUNT(*) FROM applications) AS applications_total,
            (SELECT COUNT(*) FROM jobs WHERE recommendation = 'apply') AS rec_apply,
            (SELECT COUNT(*) FROM jobs WHERE recommendation = 'review') AS rec_review,
            (SELECT COUNT(*) FROM jobs WHERE recommendation = 'skip') AS rec_skip
        """
    )
    with connection() as conn:
        row = conn.execute(sql).mappings().first()
    if row is None:
        return {}
    d = dict(row)
    for k, v in list(d.items()):
        d[k] = int(v) if v is not None else 0
    return d


def list_applications_with_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    """Applications joined to job title/company/fit for the dashboard table."""
    lim = max(1, min(int(limit), 500))
    sql = text(
        """
        SELECT a.id AS application_id, a.job_id, a.status, a.applied_at,
               a.form_filled, a.error_message,
               j.title, j.company, j.fit_score, j.recommendation, j.url, j.fit_details,
               j.description, j.terms_snippet
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        ORDER BY a.applied_at DESC NULLS LAST, a.id DESC
        LIMIT :lim
        """
    )
    with connection() as conn:
        rows = conn.execute(sql, {"lim": lim}).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(_normalize_job_row(dict(r)))
    return out


def get_fit_score_histogram() -> List[Dict[str, Any]]:
    """
    Bucket scored jobs by fit_score for charts.
    Returns rows: { bucket_label, count }.
    """
    sql = text(
        """
        SELECT
            CASE
                WHEN fit_score >= 8 THEN '8-10'
                WHEN fit_score >= 6 THEN '6-8'
                WHEN fit_score >= 4 THEN '4-6'
                WHEN fit_score >= 2 THEN '2-4'
                ELSE '0-2'
            END AS bucket_label,
            COUNT(*) AS count
        FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """
    )
    with connection() as conn:
        rows = conn.execute(sql).mappings().all()
    return [dict(r) for r in rows]


def get_recommendation_counts() -> Dict[str, int]:
    """apply / review / skip counts for charts."""
    sql = text(
        """
        SELECT recommendation, COUNT(*) AS c
        FROM jobs
        WHERE recommendation IS NOT NULL AND recommendation <> ''
        GROUP BY recommendation
        """
    )
    with connection() as conn:
        rows = conn.execute(sql).mappings().all()
    out: Dict[str, int] = {"apply": 0, "review": 0, "skip": 0}
    for r in rows:
        k = str(r.get("recommendation") or "").lower()
        if k in out:
            out[k] = int(r["c"])
    return out
