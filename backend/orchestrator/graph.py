"""LangGraph state machine wiring — full JobPilot pipeline."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from langgraph.graph import END, StateGraph

from orchestrator import nodes
from orchestrator.state import AgentState

PublishFn = Callable[[dict[str, Any]], Awaitable[None]]


def _wrap(node_fn: Callable[..., Awaitable[dict[str, Any]]], publish: PublishFn):
    async def _inner(state: AgentState) -> dict[str, Any]:
        return await node_fn(state, publish)

    return _inner


def build_graph(publish: PublishFn):
    graph = StateGraph(AgentState)
    graph.add_node("load_candidate", _wrap(nodes.node_load_candidate, publish))
    graph.add_node("job_search", _wrap(nodes.node_job_search, publish))
    graph.add_node("scoring", _wrap(nodes.node_scoring, publish))
    graph.add_node("applications", _wrap(nodes.node_applications, publish))
    graph.add_node("finalize", _wrap(nodes.node_finalize, publish))
    graph.set_entry_point("load_candidate")
    graph.add_edge("load_candidate", "job_search")
    graph.add_edge("job_search", "scoring")
    graph.add_edge("scoring", "applications")
    graph.add_edge("applications", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_full_pipeline(
    publish: PublishFn,
    candidate_id: Optional[int] = None,
) -> AgentState:
    """
    Run discover → score → (optional) apply for the given or latest candidate.

    Browser-heavy steps respect ``PLAYWRIGHT_HEADLESS`` and
    ``JOBPILOT_MAX_APPLICATIONS_PER_RUN`` (default 0 applications).
    """
    graph = build_graph(publish)
    initial: AgentState = {}
    if candidate_id is not None:
        initial["candidate_id"] = int(candidate_id)
    result = await graph.ainvoke(initial)
    return result


async def run_orchestrator(candidate_profile: dict[str, Any], publish: PublishFn) -> AgentState:
    """Run pipeline using an in-memory profile dict (e.g. tests) without a saved candidate id."""
    graph = build_graph(publish)
    initial: AgentState = {"candidate": candidate_profile, "errors": []}
    return await graph.ainvoke(initial)
