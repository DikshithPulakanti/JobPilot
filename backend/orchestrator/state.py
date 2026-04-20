"""Shared LangGraph agent state."""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """State passed between orchestrator nodes."""

    candidate_id: int
    candidate: dict[str, Any]
    jobs_found: list[dict[str, Any]]
    apply_candidates: list[dict[str, Any]]
    scoring_counts: dict[str, int]
    applications_run: list[dict[str, Any]]
    errors: list[str]
    stage: str
