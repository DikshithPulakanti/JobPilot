"""PostgreSQL helpers using SQLAlchemy (sync) and DATABASE_URL."""

import json
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

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
