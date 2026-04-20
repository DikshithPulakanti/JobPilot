"""Primary HTTP routes."""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from agents.profile_builder import build_candidate_profile
from api.events import event_hub
from orchestrator.graph import run_full_pipeline
from tracker import db as tracker_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["core"])


class StartRequest(BaseModel):
    resume_text: str = Field(..., description="Raw resume text")
    preferences: str = Field(
        default="",
        description="Free-form job search preferences (location, salary, role types, etc.)",
    )
    run_pipeline: bool = Field(
        default=False,
        description="If true, start the LangGraph pipeline (discover → score → optional apply) after saving the profile.",
    )


async def _publish_and_persist(payload: Dict[str, Any]) -> None:
    """SSE broadcast + ``events`` table (best-effort)."""
    await event_hub.publish(payload)
    try:
        details = payload.get("details")
        if details is not None and not isinstance(details, dict):
            details = {"detail": details}
        await asyncio.to_thread(
            tracker_db.insert_event,
            str(payload.get("action") or "event"),
            payload.get("company"),
            payload.get("title"),
            details if isinstance(details, dict) else {},
            payload.get("status"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("insert_event failed: %s", exc)


class PipelineRequest(BaseModel):
    candidate_id: Optional[int] = Field(
        default=None,
        description="Candidate row id; omit to use the most recently saved profile.",
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict[str, Any]:
    ok = tracker_db.healthcheck()
    return {"status": "ok" if ok else "error", "database": "connected" if ok else "unavailable"}


@router.post("/start")
async def start_run(body: StartRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Parse resume + preferences into a structured profile via Claude, persist to PostgreSQL,
    and return the profile JSON (including database id).
    """
    resume = (body.resume_text or "").strip()
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resume_text is required and cannot be empty.",
        )

    profile = await build_candidate_profile(resume, body.preferences or "")
    if profile.get("error"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=profile["error"],
        )

    try:
        candidate_id = await asyncio.to_thread(
            tracker_db.insert_candidate_profile,
            profile,
            body.preferences or "",
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "DATABASE_URL" in msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not configured (DATABASE_URL).",
            ) from exc
        logger.exception("Database insert failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=msg,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Database insert failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save candidate: {exc!s}",
        ) from exc

    out: Dict[str, Any] = {"id": candidate_id, **profile}
    if body.run_pipeline:

        async def _pipeline() -> None:
            try:
                await run_full_pipeline(_publish_and_persist, int(candidate_id))
            except Exception:
                logger.exception("Background pipeline failed")

        background_tasks.add_task(_pipeline)
        out["pipeline"] = "started"
    return out


@router.post("/run-pipeline")
async def run_pipeline_endpoint(body: PipelineRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Run discover → score → (optional) apply in the background.
    Events stream on ``GET /events`` and are persisted to ``events``.
    """

    async def _pipeline() -> None:
        try:
            await run_full_pipeline(_publish_and_persist, body.candidate_id)
        except Exception:
            logger.exception("Pipeline run failed")

    background_tasks.add_task(_pipeline)
    return {"status": "started", "candidate_id": body.candidate_id}


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Dashboard aggregate counts."""
    return await asyncio.to_thread(tracker_db.get_dashboard_metrics)


@router.get("/stats/recommendations")
async def stats_recommendations() -> dict[str, int]:
    return await asyncio.to_thread(tracker_db.get_recommendation_counts)


@router.get("/stats/fit-histogram")
async def stats_fit_histogram() -> list[dict[str, Any]]:
    return await asyncio.to_thread(tracker_db.get_fit_score_histogram)


@router.get("/applications")
async def list_applications(limit: int = 100) -> list[dict[str, Any]]:
    return await asyncio.to_thread(tracker_db.list_applications_with_jobs, limit)


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return await asyncio.to_thread(tracker_db.get_jobs, limit)
