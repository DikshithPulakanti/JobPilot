"""LangGraph node functions — wired to real agents."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

from agents.fit_scorer import score_job_fit, serialize_fit_explanation
from agents.job_finder import find_jobs
from orchestrator.retry_types import is_retryable_exception
from orchestrator.state import AgentState
from tracker import db as tracker_db

logger = logging.getLogger(__name__)

PublishFn = Callable[[dict[str, Any]], Awaitable[None]]


async def node_load_candidate(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    """Load profile from inline ``candidate``, ``candidate_id``, or latest row; publish ``pipeline_started``."""
    cand = state.get("candidate")
    if isinstance(cand, dict) and (cand.get("name") or cand.get("email")):
        prof = cand
    else:
        cid = state.get("candidate_id")
        if cid is not None:
            prof = await asyncio.to_thread(tracker_db.get_candidate_by_id, int(cid))
        else:
            prof = await asyncio.to_thread(tracker_db.get_latest_candidate_profile)

    if not prof:
        err = "No candidate profile found. Run POST /start first or pass candidate_id."
        await publish(
            {
                "action": "pipeline_error",
                "company": None,
                "title": None,
                "details": {"message": err, "failed_node": "load_candidate"},
                "status": "error",
            }
        )
        return {"errors": state.get("errors", []) + [err], "stage": "aborted"}

    await publish(
        {
            "action": "pipeline_started",
            "company": None,
            "title": None,
            "details": {
                "resume_length": 0,
                "preferences": (prof.get("preferences_text") or "")[:500],
                "candidate_id": prof.get("id"),
            },
            "status": "info",
        }
    )
    await publish(
        {
            "action": "profile_built",
            "company": None,
            "title": None,
            "details": {
                "name": prof.get("name"),
                "seniority": prof.get("seniority"),
                "visa_status": prof.get("visa_status"),
                "skills_count": len(prof.get("skills") or []),
            },
            "status": "success",
        }
    )
    return {"candidate": prof, "stage": "candidate_loaded", "errors": state.get("errors", [])}


async def node_job_search(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    """Run Indeed job discovery and persist rows."""
    if state.get("stage") == "aborted":
        return {}
    profile = state.get("candidate") or {}
    role = (profile.get("target_roles") or ["AI"])[0] if profile.get("target_roles") else "engineer"
    loc = (profile.get("preferred_locations") or ["United States"])[0]

    try:
        os.environ.setdefault("PLAYWRIGHT_HEADLESS", "true")
        jobs = await find_jobs(profile)
    except Exception as exc:  # noqa: BLE001
        if is_retryable_exception(exc):
            raise
        logger.exception("job_search failed: %s", exc)
        msg = str(exc)
        await publish(
            {
                "action": "pipeline_error",
                "company": None,
                "title": None,
                "details": {"message": msg, "failed_node": "job_search"},
                "status": "error",
            }
        )
        return {"errors": state.get("errors", []) + [msg], "stage": "aborted", "jobs_found": []}

    await publish(
        {
            "action": "jobs_found",
            "company": None,
            "title": None,
            "details": {
                "count": len(jobs),
                "source": "indeed",
                "search_query": f"{role} @ {loc}",
            },
            "status": "success",
        }
    )
    return {"jobs_found": jobs, "stage": "jobs_found"}


async def node_scoring(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    """Score each discovered job with Claude; update PostgreSQL."""
    if state.get("stage") == "aborted":
        return {}
    profile = state.get("candidate") or {}
    jobs = state.get("jobs_found") or []
    counts = {"apply": 0, "review": 0, "skip": 0}
    apply_candidates: list[dict[str, Any]] = []

    for job_row in jobs:
        job_id = int(job_row["id"])
        job = {
            "title": job_row.get("title") or "",
            "company": job_row.get("company") or "",
            "description": (job_row.get("description") or "")[:8000],
            "location": job_row.get("location") or "",
            "url": job_row.get("url") or "",
        }
        try:
            result = await score_job_fit(job, profile)
        except Exception as exc:  # noqa: BLE001
            if is_retryable_exception(exc):
                raise
            logger.warning("score failed for job %s: %s", job_id, exc)
            continue

        if result.get("error"):
            continue

        overall = float(result["overall"])
        rec = str(result["recommendation"])
        fit_details = serialize_fit_explanation(result)
        await asyncio.to_thread(
            tracker_db.update_job_score,
            job_id,
            overall,
            rec,
            fit_details=fit_details,
        )
        if rec in counts:
            counts[rec] += 1
        if rec in ("apply", "review"):
            apply_candidates.append({**job_row, "recommendation": rec, "fit_score": overall})

    await publish(
        {
            "action": "jobs_scored",
            "company": None,
            "title": None,
            "details": {
                "apply": counts["apply"],
                "review": counts["review"],
                "skip": counts["skip"],
            },
            "status": "success",
        }
    )
    return {
        "apply_candidates": apply_candidates,
        "scoring_counts": counts,
        "stage": "scored",
    }


async def node_applications(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    """
    Optionally run browser application flow for top apply/review jobs.

    Set ``JOBPILOT_MAX_APPLICATIONS_PER_RUN`` (default ``0``) to skip browser automation
    during the API pipeline (recommended for servers); use ``1`` or ``2`` to demo locally.
    """
    if state.get("stage") == "aborted":
        return {"applications_run": [], "stage": "aborted"}

    max_n = int(os.getenv("JOBPILOT_MAX_APPLICATIONS_PER_RUN", "0"))
    if max_n <= 0:
        await publish(
            {
                "action": "applications_skipped",
                "company": None,
                "title": None,
                "details": {
                    "reason": "JOBPILOT_MAX_APPLICATIONS_PER_RUN is 0",
                    "hint": "Set to 1+ to run application_runner for apply/review jobs.",
                },
                "status": "info",
            }
        )
        return {"applications_run": [], "stage": "apply_skipped"}

    from agents.application_runner import run_application_flow

    profile = state.get("candidate") or {}
    candidates = state.get("apply_candidates") or []
    out: list[dict[str, Any]] = []

    for job_row in candidates[:max_n]:
        jid = int(job_row["id"])
        try:
            await run_application_flow(jid, profile)
            out.append({"job_id": jid, "ok": True})
            await publish(
                {
                    "action": "application_filled",
                    "company": job_row.get("company"),
                    "title": job_row.get("title"),
                    "details": {
                        "job_id": jid,
                        "fields_filled": "see application row",
                        "cover_letter_preview": "",
                    },
                    "status": "success",
                }
            )
        except Exception as exc:  # noqa: BLE001
            if is_retryable_exception(exc):
                raise
            logger.exception("application_runner failed for job %s: %s", jid, exc)
            out.append({"job_id": jid, "ok": False, "error": str(exc)})
            await publish(
                {
                    "action": "pipeline_error",
                    "company": job_row.get("company"),
                    "title": job_row.get("title"),
                    "details": {"message": str(exc), "failed_node": "application_runner", "job_id": jid},
                    "status": "error",
                }
            )

    return {"applications_run": out, "stage": "applications_done"}


async def node_finalize(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    """Emit ``pipeline_completed``."""
    err = state.get("errors") or []
    if state.get("stage") == "aborted":
        await publish(
            {
                "action": "pipeline_completed",
                "company": None,
                "title": None,
                "details": {
                    "ok": False,
                    "errors": err,
                    "failed_nodes": state.get("failed_nodes") or [],
                },
                "status": "error",
            }
        )
        return {"stage": "done"}

    await publish(
        {
            "action": "pipeline_completed",
            "company": None,
            "title": None,
            "details": {
                "ok": True,
                "jobs_found": len(state.get("jobs_found") or []),
                "scoring": state.get("scoring_counts") or {},
                "applications": len(state.get("applications_run") or []),
                "failed_nodes": state.get("failed_nodes") or [],
            },
            "status": "success",
        }
    )
    return {"stage": "done"}
