"""Tailored cover letter generation via Claude."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

from anthropic import APIStatusError, AsyncAnthropic
from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_ROOT / ".env", override=True)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

BANNED_PHRASES = (
    "passionate",
    "excited",
    "i am writing to express my interest",
    "dynamic",
    "leverage",
)


def _model_name() -> str:
    return os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _truncate_words(text: str, max_words: int = 200) -> str:
    words = text.split()
    return " ".join(words[:max_words]).strip()


def _scrub_banned(text: str) -> str:
    t = text
    for phrase in BANNED_PHRASES:
        t = re.sub(re.escape(phrase), "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


async def generate_cover_letter(job: Dict[str, Any], profile: Dict[str, Any]) -> str:
    """
    Produce a tailored cover letter (plain text) for ``job`` and ``profile``.

    Uses Claude Sonnet. On failure returns a short fallback string (never raises).
    """
    if profile.get("error"):
        return "Unable to generate a cover letter because the candidate profile is invalid."

    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return "Unable to generate a cover letter: ANTHROPIC_API_KEY is not configured."

    job_block = {
        "title": str(job.get("title", "")),
        "company": str(job.get("company", "")),
        "description": str(job.get("description", ""))[:12000],
        "location": str(job.get("location", "")),
    }

    system = (
        "You write concise, human-sounding job cover letters as plain text (no subject line, no greeting line like 'Dear Hiring Manager' unless essential).\n"
        "Rules:\n"
        "- Maximum 200 words.\n"
        "- Open with why THIS specific company (use the company name and one concrete detail from the job or public role of the firm), not a generic opener.\n"
        "- Reference 2–3 specific requirements or phrases from the job description and tie each to a concrete experience, skill, or outcome from the candidate profile.\n"
        "- End with one clear call to action (e.g. willingness to discuss fit, interview availability).\n"
        "- Do NOT use these words or phrases anywhere: passionate, excited, "
        "'I am writing to express my interest', dynamic, leverage.\n"
        "- Sound natural and specific; avoid AI clichés and buzzword stacking.\n"
        "- Output only the letter body, no title, no markdown."
    )

    user = (
        "<job>\n"
        f"{json.dumps(job_block, indent=2)}\n"
        "</job>\n\n<candidate_profile>\n"
        f"{json.dumps(profile, indent=2)}\n"
        "</candidate_profile>"
    )

    client = AsyncAnthropic(api_key=api_key)
    try:
        message = await client.messages.create(
            model=_model_name(),
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except APIStatusError as exc:
        logger.warning("Anthropic error: %s", exc)
        return (
            f"Unable to generate cover letter (API {getattr(exc, 'status_code', '?')}): "
            f"{getattr(exc, 'message', str(exc))}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cover letter request failed")
        return f"Unable to generate cover letter: {exc!s}"

    parts = []
    for block in message.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    text = "".join(parts).strip()
    if not text:
        return "Unable to generate cover letter: empty model response."

    text = _scrub_banned(text)
    text = _truncate_words(text, 200)
    return text


if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        job = {
            "title": "Senior Backend Engineer",
            "company": "Klaviyo",
            "description": (
                "Build high-throughput APIs in Python and Go. "
                "Experience with Kafka, PostgreSQL, and AWS required. "
                "Collaborate with product on customer-facing reliability."
            ),
            "location": "Boston, MA",
        }
        profile = {
            "name": "Alex Rivera",
            "email": "alex@example.com",
            "skills": ["Python", "Go", "PostgreSQL", "Kafka", "AWS"],
            "experience_years": 7,
            "seniority": "senior",
            "summary": "Backend engineer focused on data pipelines and API reliability at scale.",
            "visa_status": "citizen",
            "salary_min": 180000,
            "target_roles": ["Senior Backend Engineer"],
            "preferred_locations": ["Boston", "Remote"],
            "education": ["B.S. Computer Science"],
            "phone": "617-555-0100",
            "industries": ["martech"],
            "location": "Boston, MA",
        }
        letter = await generate_cover_letter(job, profile)
        print(letter)
        print("\n--- word count ---", len(letter.split()))

    asyncio.run(_demo())
