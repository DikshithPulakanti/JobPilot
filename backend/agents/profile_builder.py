"""Resume parser and candidate profile extraction via Claude."""

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

REQUIRED_KEYS: Tuple[str, ...] = (
    "name",
    "email",
    "phone",
    "location",
    "skills",
    "experience_years",
    "seniority",
    "target_roles",
    "education",
    "visa_status",
    "salary_min",
    "preferred_locations",
    "industries",
    "summary",
)

ALLOWED_SENIORITY = frozenset({"junior", "mid", "senior"})
ALLOWED_VISA = frozenset({"citizen", "greencard", "opt", "h1b", "other"})


def _model_name() -> str:
    return os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text


def _coerce_profile(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize types and enums from parsed JSON."""

    def as_str_list(v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    seniority = str(raw.get("seniority", "mid")).lower().strip()
    if seniority not in ALLOWED_SENIORITY:
        seniority = "mid"

    visa = str(raw.get("visa_status", "other")).lower().strip().replace("-", "").replace(" ", "_")
    visa_map = {
        "greencard": "greencard",
        "green_card": "greencard",
        "permanent_resident": "greencard",
        "h1b": "h1b",
        "h1": "h1b",
        "uscitizen": "citizen",
        "us_citizen": "citizen",
    }
    visa = visa_map.get(visa, visa)
    if visa not in ALLOWED_VISA:
        visa = "other"

    exp = raw.get("experience_years", 0)
    try:
        experience_years = int(round(float(exp)))
    except (TypeError, ValueError):
        experience_years = 0

    sal = raw.get("salary_min", 0)
    try:
        salary_min = int(sal)
    except (TypeError, ValueError):
        salary_min = 0

    return {
        "name": str(raw.get("name", "")).strip() or "Unknown",
        "email": str(raw.get("email", "")).strip() or "unknown@example.com",
        "phone": str(raw.get("phone", "")).strip(),
        "location": str(raw.get("location", "")).strip(),
        "skills": as_str_list(raw.get("skills")),
        "experience_years": experience_years,
        "seniority": seniority,
        "target_roles": as_str_list(raw.get("target_roles")),
        "education": as_str_list(raw.get("education")),
        "visa_status": visa,
        "salary_min": salary_min,
        "preferred_locations": as_str_list(raw.get("preferred_locations")),
        "industries": as_str_list(raw.get("industries")),
        "summary": str(raw.get("summary", "")).strip(),
    }


def _validate_keys(data: Dict[str, Any]) -> Optional[str]:
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        return f"Missing required keys after parse: {', '.join(missing)}"
    return None


async def build_candidate_profile(resume_text: str, preferences: str) -> Dict[str, Any]:
    """
    Extract a structured candidate profile from resume text and free-form preferences.

    Returns a dict with the required profile keys on success, or ``{"error": "<message>"}``
    on failure.
    """
    resume_text = (resume_text or "").strip()
    preferences = (preferences or "").strip()

    if not resume_text:
        return {"error": "resume_text is empty."}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY is not set in the environment or .env file."}

    system = (
        "You are an expert recruiter and resume parser. "
        "You must respond with a single JSON object only — no markdown, no commentary. "
        "The JSON must contain exactly these keys and value types:\n"
        '- name: string\n- email: string\n- phone: string (use "" if unknown)\n'
        '- location: string (city, state/country)\n'
        '- skills: array of strings (technical and professional skills)\n'
        "- experience_years: integer (total years of professional experience, infer if needed)\n"
        '- seniority: one of "junior", "mid", "senior"\n'
        "- target_roles: array of strings (job titles they want)\n"
        "- education: array of strings (degree + institution + year if known)\n"
        '- visa_status: one of "citizen", "greencard", "opt", "h1b", "other"\n'
        "- salary_min: integer (minimum acceptable annual salary in USD; 0 if unknown)\n"
        "- preferred_locations: array of strings\n"
        "- industries: array of strings\n"
        "- summary: string (2–4 sentences professional summary)\n"
        "Infer reasonable values from the resume; use empty string or empty array only when truly unknown. "
        "Honor the candidate's stated preferences when they conflict with inference."
    )

    user_content = (
        "<resume>\n"
        f"{resume_text}\n"
        "</resume>\n\n"
        "<preferences>\n"
        f"{preferences if preferences else '(none)'}\n"
        "</preferences>\n\n"
        "Return only the JSON object."
    )

    client = AsyncAnthropic(api_key=api_key)
    model = _model_name()

    try:
        message = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
    except APIStatusError as exc:
        logger.warning("Anthropic API error: %s", exc)
        return {
            "error": f"Anthropic API error ({exc.status_code}): {getattr(exc, 'message', str(exc))}",
        }
    except Exception as exc:  # noqa: BLE001 — surface to caller
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
        logger.warning("JSON decode failed: %s | snippet=%s", exc, raw_text[:500])
        return {
            "error": f"Model returned invalid JSON: {exc}. First 200 chars: {raw_text[:200]!r}",
        }

    if not isinstance(payload, dict):
        return {"error": "Parsed JSON was not an object."}

    err = _validate_keys(payload)
    if err:
        return {"error": err}

    return _coerce_profile(payload)


async def build_profile_from_resume(resume_text: str) -> Dict[str, Any]:
    """Backward-compatible wrapper with no separate preferences string."""
    return await build_candidate_profile(resume_text, "")


if __name__ == "__main__":
    import asyncio

    SAMPLE_RESUME = """
Jane Doe
jane.doe@email.com | (555) 123-4567 | San Francisco, CA

SUMMARY
Software engineer with 6 years of experience building distributed systems and ML platforms.

EXPERIENCE
Senior Software Engineer | Acme Corp | 2021–Present
- Led design of real-time data pipeline (Kafka, Spark).
- Python, Go, AWS, Kubernetes.

Software Engineer | Beta Inc | 2018–2021
- Backend services in Python/Django; PostgreSQL.

EDUCATION
M.S. Computer Science, State University, 2018
B.S. Mathematics, State University, 2016

SKILLS
Python, Go, Kubernetes, AWS, PostgreSQL, Machine Learning, System Design
"""

    async def _demo() -> None:
        out = await build_candidate_profile(
            SAMPLE_RESUME,
            "Looking for senior backend or ML platform roles in SF Bay Area or remote. "
            "US citizen. Target base at least $180k. Interested in fintech and developer tools.",
        )
        print(json.dumps(out, indent=2))

    asyncio.run(_demo())
