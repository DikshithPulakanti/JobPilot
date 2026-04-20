"""LangGraph state machine wiring — full JobPilot pipeline."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Literal, Optional, TypeVar

from langgraph.graph import END, StateGraph

from orchestrator import nodes
from orchestrator.retry_types import is_retryable_exception
from orchestrator.state import AgentState
from tracker import db as tracker_db

logger = logging.getLogger(__name__)

PublishFn = Callable[[dict[str, Any]], Awaitable[None]]

T = TypeVar("T")


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay: float = 2.0,
    *,
    node_label: str = "node",
) -> tuple[Optional[T], Optional[BaseException]]:
    """
    Run ``fn`` up to ``max_attempts`` times on transient failures.

    Waits ``base_delay * 2**0``, ``base_delay * 2**1``, ... seconds between attempts
    (i.e. 2s, 4s, 8s for ``base_delay=2`` and 3 attempts).

    Returns ``(result, None)`` on success. If only retryable exceptions occur, returns
    ``(None, last_exception)`` after exhausting attempts. Non-retryable exceptions propagate.
    """
    last: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            val = await fn()
            return val, None
        except Exception as exc:
            if not is_retryable_exception(exc):
                raise
            last = exc
            if attempt >= max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s attempt %s/%s failed: %s; retrying in %ss",
                node_label,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    return None, last


async def _insert_pipeline_error_event(node_name: str, message: str) -> None:
    await asyncio.to_thread(
        tracker_db.insert_event,
        "pipeline_error",
        None,
        None,
        {"failed_node": node_name, "message": message[:4000]},
        "error",
    )


def _merge_failed_into(
    state: AgentState,
    node_name: str,
    msg: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    prev_failed = list(state.get("failed_nodes") or [])
    prev_errs = list(state.get("errors") or [])
    out = {**patch}
    out["failed_nodes"] = prev_failed + [node_name]
    out["errors"] = prev_errs + [msg]
    return out


def _merge_success(state: AgentState, result: dict[str, Any]) -> dict[str, Any]:
    """Preserve accumulated ``failed_nodes`` / ``errors`` when the node omits them."""
    out = dict(result)
    if "failed_nodes" not in out:
        out["failed_nodes"] = list(state.get("failed_nodes") or [])
    else:
        base = list(state.get("failed_nodes") or [])
        for n in out["failed_nodes"]:
            if n not in base:
                base.append(n)
        out["failed_nodes"] = base
    if "errors" not in out:
        out["errors"] = list(state.get("errors") or [])
    else:
        merged = list(state.get("errors") or [])
        for e in out["errors"]:
            if e not in merged:
                merged.append(e)
        out["errors"] = merged
    return out


def _route_after_load_candidate(state: AgentState) -> Literal["job_search", "end"]:
    """Skip job search when load failed, profile is unusable, or no candidate id is known."""
    if state.get("stage") == "aborted":
        return "end"
    profile = state.get("candidate")
    if not isinstance(profile, dict):
        return "end"
    if not str(profile.get("name") or "").strip():
        return "end"
    skills = profile.get("skills")
    if not isinstance(skills, list) or len(skills) == 0:
        return "end"
    if state.get("candidate_id") is None and profile.get("id") is None:
        return "end"
    return "job_search"


def _route_after_job_search(state: AgentState) -> Literal["scoring", "finalize"]:
    """Skip scoring and applications when nothing was discovered."""
    if len(state.get("jobs_found") or []) == 0:
        return "finalize"
    return "scoring"


def _wrap(node_fn: Callable[..., Awaitable[dict[str, Any]]], publish: PublishFn):
    async def _inner(state: AgentState) -> dict[str, Any]:
        return await node_fn(state, publish)

    return _inner


def _wrap_job_search_with_retry(
    node_fn: Callable[..., Awaitable[dict[str, Any]]],
    publish: PublishFn,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def _inner(state: AgentState) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            return await node_fn(state, publish)

        try:
            res, rerr = await retry_with_backoff(call, max_attempts=3, base_delay=2.0, node_label="job_search")
        except Exception as exc:
            await _insert_pipeline_error_event("job_search", str(exc))
            return _merge_failed_into(
                state,
                "job_search",
                f"job_search: {exc}",
                {"jobs_found": [], "stage": "jobs_found"},
            )
        if rerr is not None:
            await _insert_pipeline_error_event("job_search", str(rerr))
            return _merge_failed_into(
                state,
                "job_search",
                f"job_search: {rerr}",
                {"jobs_found": [], "stage": "jobs_found"},
            )
        return _merge_success(state, res or {})

    return _inner


def _wrap_scoring_with_retry(
    node_fn: Callable[..., Awaitable[dict[str, Any]]],
    publish: PublishFn,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def _inner(state: AgentState) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            return await node_fn(state, publish)

        try:
            res, rerr = await retry_with_backoff(call, max_attempts=3, base_delay=2.0, node_label="scoring")
        except Exception as exc:
            await _insert_pipeline_error_event("scoring", str(exc))
            return _merge_failed_into(
                state,
                "scoring",
                f"scoring: {exc}",
                {
                    "apply_candidates": [],
                    "scoring_counts": {"apply": 0, "review": 0, "skip": 0},
                    "stage": "scored",
                },
            )
        if rerr is not None:
            await _insert_pipeline_error_event("scoring", str(rerr))
            return _merge_failed_into(
                state,
                "scoring",
                f"scoring: {rerr}",
                {
                    "apply_candidates": [],
                    "scoring_counts": {"apply": 0, "review": 0, "skip": 0},
                    "stage": "scored",
                },
            )
        return _merge_success(state, res or {})

    return _inner


def _wrap_applications_with_retry(
    node_fn: Callable[..., Awaitable[dict[str, Any]]],
    publish: PublishFn,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def _inner(state: AgentState) -> dict[str, Any]:
        async def call() -> dict[str, Any]:
            return await node_fn(state, publish)

        try:
            res, rerr = await retry_with_backoff(call, max_attempts=3, base_delay=2.0, node_label="applications")
        except Exception as exc:
            await _insert_pipeline_error_event("applications", str(exc))
            return _merge_failed_into(
                state,
                "applications",
                f"applications: {exc}",
                {"applications_run": [], "stage": "applications_done"},
            )
        if rerr is not None:
            await _insert_pipeline_error_event("applications", str(rerr))
            return _merge_failed_into(
                state,
                "applications",
                f"applications: {rerr}",
                {"applications_run": [], "stage": "applications_done"},
            )
        return _merge_success(state, res or {})

    return _inner


def build_graph(publish: PublishFn):
    graph = StateGraph(AgentState)
    graph.add_node("load_candidate", _wrap(nodes.node_load_candidate, publish))
    graph.add_node("job_search", _wrap_job_search_with_retry(nodes.node_job_search, publish))
    graph.add_node("scoring", _wrap_scoring_with_retry(nodes.node_scoring, publish))
    graph.add_node("applications", _wrap_applications_with_retry(nodes.node_applications, publish))
    graph.add_node("finalize", _wrap(nodes.node_finalize, publish))
    graph.set_entry_point("load_candidate")
    graph.add_conditional_edges(
        "load_candidate",
        _route_after_load_candidate,
        {"job_search": "job_search", "end": END},
    )
    graph.add_conditional_edges(
        "job_search",
        _route_after_job_search,
        {"scoring": "scoring", "finalize": "finalize"},
    )
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


# Example: `cd backend && python -m orchestrator.graph` (requires `resume.txt` in `backend/`)
if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    _BACKEND_ROOT = Path(__file__).resolve().parents[1]
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))

    from dotenv import load_dotenv

    load_dotenv(_BACKEND_ROOT / ".env", override=True)

    from agents.profile_builder import build_candidate_profile
    from tracker import db as tracker_db

    PREFERENCES = (
        "Remote-friendly software engineering roles in the US. "
        "Prefer Python, backend, or ML. Avoid defense contractors."
    )

    async def _noop_publish(_: dict[str, Any]) -> None:
        return None

    async def _cli() -> None:
        resume_path = _BACKEND_ROOT / "resume.txt"
        if not resume_path.is_file():
            print(f"Missing {resume_path}. Add a plain-text resume there and retry.")
            sys.exit(1)
        resume_text = resume_path.read_text(encoding="utf-8")
        profile = await build_candidate_profile(resume_text, PREFERENCES)
        if profile.get("error"):
            print("Profile build failed:", profile.get("error"))
            sys.exit(1)
        candidate_id = await asyncio.to_thread(
            tracker_db.insert_candidate_profile,
            profile,
            PREFERENCES,
        )
        result = await run_full_pipeline(_noop_publish, candidate_id)
        jobs_found = len(result.get("jobs_found") or [])
        sc = result.get("scoring_counts") or {}
        jobs_scored = sum(int(sc.get(k, 0)) for k in ("apply", "review", "skip"))
        applied = len(result.get("applications_run") or [])
        print("=== Pipeline summary ===")
        print(f"Total jobs found: {jobs_found}")
        print(f"Total jobs scored: {jobs_scored}")
        print(f"Total applications run: {applied}")
        errs = result.get("errors") or []
        if errs:
            print(f"Errors ({len(errs)}):", errs)

    asyncio.run(_cli())
