"""Batch-score unscored jobs in PostgreSQL using the latest candidate profile."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import text

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

load_dotenv(_BACKEND_ROOT / ".env", override=True)

from agents.fit_scorer import score_job_fit  # noqa: E402
from tracker.db import connection, get_unscored_jobs, update_job_score  # noqa: E402

logger = logging.getLogger(__name__)


def _fetch_latest_candidate_profile() -> Optional[Dict[str, Any]]:
    """Load the most recent row from ``candidates`` as a profile dict."""
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

    d = dict(row)

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


async def run_scoring_pipeline(limit: int = 50) -> None:
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        print(
            "ANTHROPIC_API_KEY is missing or empty. Add it to backend/.env, e.g.\n"
            "  ANTHROPIC_API_KEY=sk-ant-api03-...\n"
            "If you previously ran `export ANTHROPIC_API_KEY=...` in this terminal, "
            "unset it or fix it: `unset ANTHROPIC_API_KEY` then rely on .env."
        )
        return

    profile = _fetch_latest_candidate_profile()
    if not profile:
        print("No candidates in database; insert a profile before scoring jobs.")
        return

    jobs = get_unscored_jobs(limit=limit)
    if not jobs:
        print("No unscored jobs found (fit_score IS NULL).")
        return

    scored_rows: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    counts = {"apply": 0, "review": 0, "skip": 0}
    errors = 0

    for job_row in jobs:
        job_id = int(job_row["id"])
        job = {
            "title": job_row.get("title") or "",
            "company": job_row.get("company") or "",
            "description": (job_row.get("description") or "")[:8000],
            "location": job_row.get("location") or "",
            "url": job_row.get("url") or "",
        }

        title = job["title"]
        company = job["company"]
        print(f"Scoring: {title} @ {company}...")

        result = await score_job_fit(job, profile)
        if result.get("error"):
            print(f"  Error: {result['error']}")
            errors += 1
            await asyncio.sleep(1.0)
            continue

        overall = float(result["overall"])
        rec = str(result["recommendation"])
        print(f"  -> overall={overall} recommendation={rec}")

        update_job_score(job_id, overall, rec)
        if rec in counts:
            counts[rec] += 1
        scored_rows.append((job_row, result))
        await asyncio.sleep(1.0)

    total_scored = len(scored_rows)
    print()
    print("=== Summary ===")
    print(f"Total jobs scored: {total_scored}")
    if errors:
        print(f"Failed / skipped (API or validation): {errors}")
    print(f"apply: {counts['apply']}  |  review: {counts['review']}  |  skip: {counts['skip']}")

    ranked = sorted(
        scored_rows,
        key=lambda pair: float(pair[1]["overall"]),
        reverse=True,
    )[:3]
    print()
    print("Top 3 by score:")
    for jr, res in ranked:
        print(
            f"  {res['overall']:.2f}  {res['recommendation']:6}  "
            f"{jr.get('title')} @ {jr.get('company')}"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scoring_pipeline(limit=100))
