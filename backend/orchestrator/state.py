"""Shared LangGraph agent state."""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """State passed between orchestrator nodes."""

    candidate: dict[str, Any]
    stage: str
    jobs_found: list[dict[str, Any]]
    errors: list[str]
