"""LangGraph node functions."""

from typing import Any, Awaitable, Callable

from orchestrator.state import AgentState

PublishFn = Callable[[dict[str, Any]], Awaitable[None]]


async def node_ingest_candidate(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    await publish(
        {
            "action": "ingest_candidate",
            "company": None,
            "title": None,
            "details": {"name": state.get("candidate", {}).get("name")},
            "status": "running",
        }
    )
    return {"stage": "ingest_complete"}


async def node_plan_search(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    await publish(
        {
            "action": "plan_job_search",
            "company": None,
            "title": None,
            "details": {"target_roles": state.get("candidate", {}).get("target_roles", [])},
            "status": "running",
        }
    )
    return {"stage": "search_planned"}


async def node_finalize(state: AgentState, publish: PublishFn) -> dict[str, Any]:
    await publish(
        {
            "action": "orchestrator_complete",
            "company": None,
            "title": None,
            "details": {"stage": state.get("stage")},
            "status": "success",
        }
    )
    return {"stage": "done", "jobs_found": state.get("jobs_found", [])}
