"""LLM-based multi-dimensional job fit scoring via Claude."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from anthropic import APIStatusError, AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

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

ALLOWED_RECOMMENDATIONS = frozenset({"apply", "skip", "review"})


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


def _weighted_overall(scores_block: Dict[str, Any]) -> float:
    total = 0.0
    for key, w in WEIGHTS.items():
        block = scores_block.get(key) or {}
        if isinstance(block, dict):
            s = _clamp_score(block.get("score"))
        else:
            s = _clamp_score(block)
        total += s * w
    return round(total, 2)


def _recommendation_from_overall(overall: float, model_rec: str) -> str:
    rec = model_rec.lower().strip()
    if rec in ALLOWED_RECOMMENDATIONS:
        return rec
    if overall >= 7.5:
        return "apply"
    if overall < 5.0:
        return "skip"
    return "review"


async def score_fit(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score how well a job posting fits a candidate profile.

    ``job`` should include: title, company, description, location, url.
    ``profile`` should match the structure returned by ``build_candidate_profile``.

    On failure returns ``{"error": "<message>"}``.
    """
    if profile.get("error"):
        return {"error": f"Invalid profile: {profile.get('error')}"}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY is not set in the environment or .env file."}

    required_job = ("title", "company", "description", "location", "url")
    for k in required_job:
        if k not in job:
            return {"error": f"job dict missing required key: {k}"}
    for k in ("title", "company", "description", "url"):
        if not str(job.get(k, "")).strip():
            return {"error": f"job.{k} must be a non-empty string"}

    job_block = {
        "title": str(job.get("title", "")),
        "company": str(job.get("company", "")),
        "description": str(job.get("description", "")),
        "location": str(job.get("location", "")),
        "url": str(job.get("url", "")),
    }

    system = (
        "You are an expert technical recruiter. Score job-candidate fit on five dimensions. "
        "Each dimension: integer score 0–10 and a single concise reason (one short sentence). "
        "Respond with a single JSON object only — no markdown, no extra text.\n\n"
        "JSON shape:\n"
        "{\n"
        '  "scores": {\n'
        '    "skills_match": {"score": <0-10 int>, "reason": "<one line>"},\n'
        '    "experience_level": {"score": ..., "reason": "..."},\n'
        '    "location_fit": {"score": ..., "reason": "..."},\n'
        '    "visa_compatible": {"score": ..., "reason": "..."},\n'
        '    "salary_likely": {"score": ..., "reason": "..."}\n'
        "  },\n"
        '  "recommendation": "apply" | "skip" | "review",\n'
        '  "reasoning": "<one sentence summary>",\n'
        '  "red_flags": ["<string>", ...]\n'
        "}\n\n"
        "Guidelines:\n"
        "- skills_match: overlap between job requirements and candidate skills.\n"
        "- experience_level: seniority and years vs job expectations.\n"
        "- location_fit: remote/hybrid/onsite vs candidate location and preferred_locations.\n"
        "- visa_compatible: sponsorship needs vs candidate visa_status.\n"
        "- salary_likely: whether compensation is plausibly aligned with salary_min (infer from level/location if not stated).\n"
        "Use red_flags for serious mismatches (e.g., hard skill gaps, visa mismatch, location impossible)."
    )

    user_content = (
        "<job>\n"
        f"{json.dumps(job_block, indent=2)}\n"
        "</job>\n\n"
        "<candidate_profile>\n"
        f"{json.dumps(profile, indent=2)}\n"
        "</candidate_profile>\n\n"
        "Return only the JSON object."
    )

    client = AsyncAnthropic(api_key=api_key)
    model = _model_name()

    try:
        message = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except APIStatusError as exc:
        logger.warning("Anthropic API error: %s", exc)
        return {
            "error": f"Anthropic API error ({exc.status_code}): {getattr(exc, 'message', str(exc))}",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error calling Anthropic")
        return {"error": f"Request failed: {exc!s}"}

    parts: List[str] = []
    for block in message.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    raw_text = "".join(parts).strip()
    if not raw_text:
        return {"error": "Empty response from the model."}

    try:
        payload = json.loads(_strip_json_fence(raw_text))
    except json.JSONDecodeError as exc:
        logger.warning("JSON decode failed: %s", exc)
        return {"error": f"Model returned invalid JSON: {exc}. First 200 chars: {raw_text[:200]!r}"}

    if not isinstance(payload, dict):
        return {"error": "Parsed JSON was not an object."}

    scores_raw = payload.get("scores")
    if not isinstance(scores_raw, dict):
        return {"error": 'Response missing valid "scores" object.'}

    normalized_scores: Dict[str, Dict[str, Any]] = {}
    for dim in DIMENSIONS:
        block = scores_raw.get(dim)
        if isinstance(block, dict):
            normalized_scores[dim] = {
                "score": _clamp_score(block.get("score")),
                "reason": str(block.get("reason", "")).strip() or "No reason provided.",
            }
        else:
            normalized_scores[dim] = {"score": 0, "reason": "Not provided by model."}

    overall = _weighted_overall(normalized_scores)
    reasoning = str(payload.get("reasoning", "")).strip() or "No summary provided."
    red_flags = payload.get("red_flags")
    if isinstance(red_flags, list):
        red_flags_list = [str(x).strip() for x in red_flags if str(x).strip()]
    else:
        red_flags_list = []

    recommendation = _recommendation_from_overall(
        overall,
        str(payload.get("recommendation", "")),
    )

    return {
        "scores": normalized_scores,
        "overall": overall,
        "recommendation": recommendation,
        "reasoning": reasoning,
        "red_flags": red_flags_list,
    }


if __name__ == "__main__":
    import asyncio

    SAMPLE_PROFILE = {
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

    SAMPLE_JOB = {
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
        out = await score_fit(SAMPLE_JOB, SAMPLE_PROFILE)
        print(json.dumps(out, indent=2))

    asyncio.run(_demo())
