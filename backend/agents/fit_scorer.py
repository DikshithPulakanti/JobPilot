"""LLM-based multi-dimensional job fit scoring via Claude (Anthropic)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from anthropic import APIStatusError, AsyncAnthropic
from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
# override=True: backend/.env wins over empty/wrong keys exported in the parent shell
load_dotenv(_BACKEND_ROOT / ".env", override=True)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

DIMENSIONS: Tuple[str, ...] = (
    "skills_match",
    "experience_level",
    "location_fit",
    "visa_compatible",
    "salary_likely",
)

WEIGHTS: Dict[str, float] = {
    "skills_match": 0.35,
    "experience_level": 0.25,
    "location_fit": 0.20,
    "visa_compatible": 0.10,
    "salary_likely": 0.10,
}


def _model_name() -> str:
    return os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _clamp_score(n: Any) -> int:
    try:
        v = int(round(float(n)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, v))


def _weighted_overall(scores_block: Dict[str, Dict[str, Any]]) -> float:
    total = 0.0
    for key, w in WEIGHTS.items():
        block = scores_block.get(key) or {}
        s = _clamp_score(block.get("score"))
        total += s * w
    return round(total, 2)


def _recommendation_from_overall(overall: float) -> str:
    if overall >= 7.0:
        return "apply"
    if overall >= 5.0:
        return "review"
    return "skip"


def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """Parse first JSON object from model text; return None if invalid."""
    if not raw_text or not raw_text.strip():
        return None
    cleaned = _strip_json_fence(raw_text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _normalize_claude_payload(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate and build the final result dict, or None if structure is wrong."""
    scores_raw = payload.get("scores")
    if not isinstance(scores_raw, dict):
        return None

    normalized_scores: Dict[str, Dict[str, Any]] = {}
    for dim in DIMENSIONS:
        block = scores_raw.get(dim)
        if not isinstance(block, dict):
            return None
        score = _clamp_score(block.get("score"))
        reason = str(block.get("reason", "")).strip()
        if not reason:
            reason = "No reason provided."
        normalized_scores[dim] = {"score": score, "reason": reason}

    overall = _weighted_overall(normalized_scores)
    reasoning = str(payload.get("reasoning", "")).strip() or "No summary provided."
    red_flags = payload.get("red_flags")
    if isinstance(red_flags, list):
        red_flags_list = [str(x).strip() for x in red_flags if str(x).strip()]
    else:
        red_flags_list = []

    recommendation = _recommendation_from_overall(overall)

    return {
        "scores": normalized_scores,
        "overall": overall,
        "recommendation": recommendation,
        "reasoning": reasoning,
        "red_flags": red_flags_list,
    }


def _build_system_prompt() -> str:
    return (
        "You are an expert technical recruiter. Score job-candidate fit on exactly five dimensions. "
        "Each dimension: integer score 0–10 and exactly one concise sentence as the reason.\n\n"
        "Respond with a single JSON object only — no markdown fences, no commentary before or after.\n\n"
        "Required JSON shape:\n"
        "{\n"
        '  "scores": {\n'
        '    "skills_match": {"score": <int 0-10>, "reason": "<one line>"},\n'
        '    "experience_level": {"score": <int>, "reason": "<one line>"},\n'
        '    "location_fit": {"score": <int>, "reason": "<one line>"},\n'
        '    "visa_compatible": {"score": <int>, "reason": "<one line>"},\n'
        '    "salary_likely": {"score": <int>, "reason": "<one line>"}\n'
        "  },\n"
        '  "reasoning": "<one sentence overall summary>",\n'
        '  "red_flags": ["<optional strings>", ...]\n'
        "}\n\n"
        "Dimension guidance:\n"
        "- skills_match: overlap between job requirements and candidate skills.\n"
        "- experience_level: seniority and years vs job expectations.\n"
        "- location_fit: remote/hybrid/onsite vs candidate location and preferred_locations.\n"
        "- visa_compatible: sponsorship needs vs candidate visa_status.\n"
        "- salary_likely: compensation alignment with candidate salary_min (infer from level/location if needed).\n"
        "Use red_flags only for serious mismatches (empty array if none)."
    )


async def _call_claude(
    client: AsyncAnthropic,
    model: str,
    job_block: Dict[str, Any],
    profile: Dict[str, Any],
    retry_hint: str,
) -> str:
    user_parts = [
        "<job>\n",
        json.dumps(job_block, indent=2),
        "\n</job>\n\n<candidate_profile>\n",
        json.dumps(profile, indent=2),
        "\n</candidate_profile>\n\n",
        "Return only the JSON object.",
    ]
    if retry_hint:
        user_parts.insert(0, retry_hint + "\n\n")

    message = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=_build_system_prompt(),
        messages=[{"role": "user", "content": "".join(user_parts)}],
    )
    parts: List[str] = []
    for block in message.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "".join(parts).strip()


async def score_job_fit(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score how well a job fits a candidate profile using Claude.

    ``job`` must include keys: title, company, url, and may include description and location
    (Indeed imports often have no description — an empty description is allowed).

    Returns keys: scores, overall, recommendation, reasoning, red_flags.
    On failure returns ``{"error": "<message>"}``.
    """
    if profile.get("error"):
        return {"error": f"Invalid profile: {profile.get('error')}"}

    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return {
            "error": (
                "ANTHROPIC_API_KEY is missing or empty. Set it in backend/.env "
                "(no quotes; no spaces around the = sign)."
            ),
        }

    required_keys = ("title", "company", "url", "description", "location")
    for k in required_keys:
        if k not in job:
            return {"error": f"job dict missing required key: {k}"}

    for k in ("title", "company", "url"):
        if not str(job.get(k, "")).strip():
            return {"error": f"job.{k} must be a non-empty string"}

    desc = str(job.get("description", "") or "").strip()
    if not desc:
        desc = (
            "(No job description was stored for this listing. "
            "Infer fit from title, company, location, and URL only; "
            "score conservatively where information is missing.)"
        )

    job_block = {
        "title": str(job.get("title", "")),
        "company": str(job.get("company", "")),
        "description": desc,
        "location": str(job.get("location", "")),
        "url": str(job.get("url", "")),
    }

    client = AsyncAnthropic(api_key=api_key)
    model = _model_name()

    retry_hint = ""
    last_raw = ""

    for attempt in range(2):
        try:
            last_raw = await _call_claude(client, model, job_block, profile, retry_hint)
        except APIStatusError as exc:
            logger.warning("Anthropic API error: %s", exc)
            if getattr(exc, "status_code", None) == 401:
                return {
                    "error": (
                        "Anthropic returned 401 (invalid API key). Copy a fresh key from "
                        "https://console.anthropic.com/ into backend/.env as ANTHROPIC_API_KEY=sk-ant-... "
                        "No quotes around the value. If the shell has ANTHROPIC_API_KEY exported, run "
                        "`unset ANTHROPIC_API_KEY` so backend/.env is used."
                    ),
                }
            return {
                "error": (
                    f"Anthropic API error ({exc.status_code}): "
                    f"{getattr(exc, 'message', str(exc))}"
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error calling Anthropic")
            return {"error": f"Request failed: {exc!s}"}

        if not last_raw:
            if attempt == 0:
                retry_hint = "Your previous response was empty. Reply with only one valid JSON object."
                continue
            return {"error": "Empty response from the model after retry."}

        payload = _extract_json_object(last_raw)
        if payload is None:
            if attempt == 0:
                logger.warning("Invalid JSON from Claude; retrying once.")
                retry_hint = (
                    "Your previous reply was not valid JSON or did not match the required schema. "
                    "Reply again with ONLY one JSON object: scores (all five dimensions with score and reason), "
                    "reasoning (string), red_flags (array of strings, may be empty). No markdown."
                )
                continue
            return {
                "error": (
                    "Model returned invalid JSON twice. "
                    f"Last snippet: {last_raw[:300]!r}"
                ),
            }

        result = _normalize_claude_payload(payload)
        if result is None:
            if attempt == 0:
                logger.warning("JSON schema mismatch; retrying once.")
                retry_hint = (
                    "Your JSON was parseable but invalid: scores must include exactly these keys: "
                    "skills_match, experience_level, location_fit, visa_compatible, salary_likely — "
                    "each an object with score (0-10 int) and reason (string). "
                    "Also include reasoning (string) and red_flags (array). Reply with only that JSON object."
                )
                continue
            return {"error": "Model response did not match the required scores schema after retry."}

        return result

    return {"error": "Unexpected scoring loop exit."}


async def score_fit(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Alias for :func:`score_job_fit` (backward compatible argument order: job, profile)."""
    return await score_job_fit(job, profile)


if __name__ == "__main__":
    import asyncio

    SAMPLE_PROFILE: Dict[str, Any] = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "",
        "location": "San Francisco, CA",
        "skills": ["Python", "Kubernetes", "AWS", "PostgreSQL", "Go"],
        "experience_years": 6,
        "seniority": "senior",
        "target_roles": ["Senior Backend Engineer", "ML Platform Engineer"],
        "education": ["M.S. Computer Science, 2018"],
        "visa_status": "citizen",
        "salary_min": 180000,
        "preferred_locations": ["San Francisco Bay Area", "Remote"],
        "industries": ["fintech", "developer tools"],
        "summary": "Backend engineer focused on distributed systems and data platforms.",
    }

    SAMPLE_JOB: Dict[str, Any] = {
        "title": "Senior Backend Engineer",
        "company": "PayStream",
        "description": (
            "We need a senior backend engineer with strong Python and PostgreSQL. "
            "Experience with payment systems and AWS required. On-site 3 days/week in San Francisco. "
            "Base range $190k–$230k. US work authorization required; we do not sponsor visas at this time."
        ),
        "location": "San Francisco, CA (hybrid)",
        "url": "https://example.com/jobs/12345",
    }

    async def _demo() -> None:
        out = await score_job_fit(SAMPLE_JOB, SAMPLE_PROFILE)
        print(json.dumps(out, indent=2))

    asyncio.run(_demo())
