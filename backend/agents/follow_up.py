"""Application follow-up scheduling."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def schedule_follow_up(application_id: int, when: Optional[datetime] = None) -> dict[str, Any]:
    """Schedule a follow-up reminder for an application."""
    run_at = when or (datetime.now(timezone.utc) + timedelta(days=7))
    return {"application_id": application_id, "follow_up_at": run_at.isoformat() + "Z"}
