"""Primary HTTP routes."""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agents.profile_builder import build_candidate_profile
from tracker import db as tracker_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["core"])


class StartRequest(BaseModel):
    resume_text: str = Field(..., description="Raw resume text")
    preferences: str = Field(
        default="",
        description="Free-form job search preferences (location, salary, role types, etc.)",
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db() -> dict[str, Any]:
    ok = tracker_db.healthcheck()
    return {"database": "ok" if ok else "unavailable"}


@router.post("/start")
async def start_run(body: StartRequest) -> dict[str, Any]:
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

    return {"id": candidate_id, **profile}
