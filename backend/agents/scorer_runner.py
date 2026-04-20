"""Batch-score unscored jobs in PostgreSQL using the latest candidate profile."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

load_dotenv(_BACKEND_ROOT / ".env", override=True)

from agents.fit_scorer import score_job_fit, serialize_fit_explanation  # noqa: E402
from tracker.db import get_latest_candidate_profile, get_unscored_jobs, update_job_score  # noqa: E402

logger = logging.getLogger(__name__)


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

    profile = get_latest_candidate_profile()
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

        update_job_score(job_id, overall, rec, fit_details=serialize_fit_explanation(result))
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
