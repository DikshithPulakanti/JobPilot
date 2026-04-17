"""LangGraph state machine wiring."""

from typing import Any, Awaitable, Callable

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
    graph.add_node("ingest_candidate", _wrap(nodes.node_ingest_candidate, publish))
    graph.add_node("plan_job_search", _wrap(nodes.node_plan_search, publish))
    graph.add_node("finalize", _wrap(nodes.node_finalize, publish))
    graph.set_entry_point("ingest_candidate")
    graph.add_edge("ingest_candidate", "plan_job_search")
    graph.add_edge("plan_job_search", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_orchestrator(candidate_profile: dict[str, Any], publish: PublishFn) -> AgentState:
    """Execute the orchestration graph for a candidate profile."""
    graph = build_graph(publish)
    initial: AgentState = {"candidate": candidate_profile, "jobs_found": [], "errors": []}
    result = await graph.ainvoke(initial)
    return result
