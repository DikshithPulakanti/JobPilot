"""Playwright-based Indeed job discovery with optional GPT-4o vision fallback."""

from __future__ import annotations

import sys
from pathlib import Path

# Running as `python agents/job_finder.py` puts `agents/` on sys.path, not `backend/`.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import asyncio
import base64
import json
import logging
import os
import random
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs

from dotenv import load_dotenv
from openai import APIError, AsyncOpenAI, RateLimitError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from tracker import db as tracker_db

load_dotenv(_BACKEND_ROOT / ".env")
load_dotenv()

logger = logging.getLogger(__name__)

INDEED_BASE = "https://www.indeed.com/jobs"
MAX_DESC_LEN = 1000
MIN_DOM_RESULTS = 3


def _playwright_headless() -> bool:
    """Headless for API/server pipelines; default false for local CLI demos."""
    return os.getenv("PLAYWRIGHT_HEADLESS", "").lower() in ("1", "true", "yes")


async def _delay_action() -> None:
    await asyncio.sleep(random.uniform(2.0, 5.0))


def _first_role(profile: Dict[str, Any]) -> str:
    roles = profile.get("target_roles") or []
    if isinstance(roles, list) and roles:
        return str(roles[0]).strip()
    return "software engineer"


def _first_location(profile: Dict[str, Any]) -> str:
    locs = profile.get("preferred_locations") or []
    if isinstance(locs, list) and locs:
        return str(locs[0]).strip()
    loc = str(profile.get("location", "") or "").strip()
    if loc:
        return loc
    return "United States"


def _indeed_search_url(role: str, location: str) -> str:
    q = quote_plus(role)
    l = quote_plus(location)
    return f"{INDEED_BASE}?q={q}&l={l}"


def _normalize_indeed_url(href: Optional[str]) -> str:
    """Build an absolute Indeed URL; keep query params (e.g. viewjob?jk=...)."""
    if not href or not isinstance(href, str):
        return ""
    href = href.strip()
    if href.startswith("http"):
        full = href
    elif href.startswith("/"):
        full = urljoin("https://www.indeed.com", href)
    else:
        full = urljoin("https://www.indeed.com", "/" + href.lstrip("/"))
    return full.split("#")[0]


def _jk_from_href(href: str) -> Optional[str]:
    if not href:
        return None
    if "jk=" in href:
        parsed = urlparse(href if href.startswith("http") else f"https://www.indeed.com{href}")
        qs = parse_qs(parsed.query)
        jk = qs.get("jk", [None])[0]
        if jk:
            return jk.split("&")[0].strip()
    m = re.search(r"[?&]jk=([^&]+)", href)
    if not m:
        return None
    return m.group(1).strip()


_JK_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_-]{8,40}$")


def _valid_jk(jk: Optional[str]) -> bool:
    if not jk or not isinstance(jk, str):
        return False
    return bool(_JK_TOKEN_RE.match(jk.strip()))


def _is_tracking_job_url(url: str) -> bool:
    """Indeed sponsored / redirect links — not stable job record URLs."""
    if not url:
        return True
    u = url.lower()
    if "pagead" in u or "/pagead/" in u:
        return True
    if "indeed.com/clk" in u and "viewjob" not in u:
        return True
    if "mo=r" in u and "viewjob" not in u:
        return True
    return False


def _canonical_viewjob_url(jk: str) -> str:
    return f"https://www.indeed.com/viewjob?jk={jk.strip()}"


async def _resolve_jk_from_card(card: Any) -> Optional[str]:
    """Get a stable job key from data attributes or organic links only."""
    raw = await card.get_attribute("data-jk")
    if _valid_jk(raw):
        return raw.strip()

    inner = card.locator("[data-jk]").first
    if await inner.count():
        inner_jk = await inner.get_attribute("data-jk")
        if _valid_jk(inner_jk):
            return inner_jk.strip()

    link_selectors = (
        'a[href*="/viewjob?jk="]',
        'a[href*="viewjob?jk="]',
        'a[href*="/viewjob"]',
        'a.jcs-JobTitle[href*="jk="]',
        'a[href*="/rc/clk?jk="]',
        'a[href*="/rc/clk"]',
    )
    for sel in link_selectors:
        link = card.locator(sel).first
        if await link.count() == 0:
            continue
        href = await link.get_attribute("href") or ""
        full = _normalize_indeed_url(href)
        if _is_tracking_job_url(full):
            continue
        jk = _jk_from_href(full)
        if _valid_jk(jk):
            return jk
    return None


async def _try_dismiss_consent(page: Any) -> None:
    selectors = [
        'button:has-text("Accept")',
        'button:has-text("accept")',
        'button[id="onetrust-accept-btn-handler"]',
        'button:has-text("I agree")',
        'button:has-text("Got it")',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=3000)
                await _delay_action()
                return
        except Exception:  # noqa: BLE001
            continue


async def _extract_card(
    card: Any,
) -> Optional[Dict[str, Any]]:
    try:
        jk = await _resolve_jk_from_card(card)
        if not jk:
            return None

        title = ""
        title_link = card.locator("a.jcs-JobTitle, h2.jobTitle a, span.jcs-JobTitle a").first
        if await title_link.count():
            title = (await title_link.inner_text()).strip()
        if not title:
            fallback = card.locator("h2.jobTitle, span[id^='jobTitle-']").first
            if await fallback.count():
                title = (await fallback.inner_text()).strip()
        if not title:
            title = "Untitled role"

        url = _canonical_viewjob_url(jk)
        if _is_tracking_job_url(url):
            return None

        company = ""
        for csel in (
            '[data-testid="company-name"]',
            "span.companyName",
            "div.company_location > div:first-child",
            "span[class*='companyName']",
        ):
            cl = card.locator(csel).first
            if await cl.count():
                company = (await cl.inner_text()).strip()
                if company:
                    break

        location = ""
        for lsel in (
            '[data-testid="text-location"]',
            "div.companyLocation",
            "div.company_location",
        ):
            ll = card.locator(lsel).first
            if await ll.count():
                location = (await ll.inner_text()).strip()
                if location:
                    break

        description = ""
        for dsel in (
            "div.jobCardShelfContainer",
            "table.jobCardMain",
            "div.underShelfFooter",
            "div[class*='jobCard']",
        ):
            dl = card.locator(dsel).first
            if await dl.count():
                description = (await dl.inner_text()).strip()
                if description:
                    break

        if len(description) > MAX_DESC_LEN:
            description = description[:MAX_DESC_LEN]

        return {
            "title": title,
            "company": company or "Unknown company",
            "location": location,
            "url": url,
            "description": description,
            "source": "indeed",
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Card parse skipped: %s", exc)
        return None


async def _extract_jobs_dom(page: Any) -> List[Dict[str, Any]]:
    """Prefer full job cards; avoid bare ``div[data-jk]`` nodes (often ads / fragments)."""
    seen_jk: set[str] = set()
    jobs: List[Dict[str, Any]] = []

    container_selectors = (
        "div.job_seen_beacon",
        "li.resultContent",
    )

    for csel in container_selectors:
        cards = page.locator(csel)
        n = await cards.count()
        if n == 0:
            continue
        for i in range(n):
            card = cards.nth(i)
            row = await _extract_card(card)
            if not row:
                continue
            jk = _jk_from_href(row["url"])
            if not jk or jk in seen_jk:
                continue
            seen_jk.add(jk)
            jobs.append(row)
        if len(jobs) >= MIN_DOM_RESULTS:
            break

    return jobs


async def _extract_jobs_vision(page: Any) -> List[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY missing; cannot run vision fallback.")
        return []

    await _delay_action()
    png = await page.screenshot(full_page=True, type="png")
    b64 = base64.standard_b64encode(png).decode("ascii")

    client = AsyncOpenAI(api_key=api_key)
    prompt = (
        "This is a screenshot of Indeed job search results. "
        "Extract every distinct ORGANIC job listing you can read (ignore sponsored ad blocks). "
        "Return a single JSON array only (no markdown). "
        "Each element must be an object with keys: "
        'title (string), company (string), location (string), '
        "url (string): MUST be exactly https://www.indeed.com/viewjob?jk=<id> where <id> is the "
        "visible job id from the card (often 16 alphanumeric characters). "
        "Never use pagead, clk, or tracking URLs. If you cannot read a real viewjob jk, omit that job. "
        f'description (string, up to {MAX_DESC_LEN} characters from visible snippet), '
        'source (string, always exactly "indeed"). '
        "Omit duplicate listings (same jk)."
    )

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )
    except (RateLimitError, APIError) as exc:
        logger.exception("OpenAI vision request failed: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAI vision unexpected error: %s", exc)
        return []

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        return []

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text, flags=re.IGNORECASE)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            logger.warning("Vision response not valid JSON: %s", text[:400])
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []

    if not isinstance(data, list):
        return []

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip() or "Untitled role"
        company = str(item.get("company", "")).strip() or "Unknown company"
        location = str(item.get("location", "")).strip()
        url = str(item.get("url", "")).strip()
        norm = _normalize_indeed_url(url)
        if not norm or "indeed.com" not in norm or _is_tracking_job_url(norm):
            continue
        jk_parsed = _jk_from_href(norm)
        if not _valid_jk(jk_parsed):
            continue
        canon = _canonical_viewjob_url(jk_parsed)
        desc = str(item.get("description", "")).strip()
        if len(desc) > MAX_DESC_LEN:
            desc = desc[:MAX_DESC_LEN]
        rec = {
            "title": title,
            "company": company,
            "location": location,
            "url": canon,
            "description": desc,
            "source": "indeed",
        }
        if canon not in seen:
            seen.add(canon)
            out.append(rec)
    return out


async def find_jobs(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Search Indeed using the first ``target_roles`` and first ``preferred_locations`` entry,
    extract job postings (DOM first, GPT-4o vision if needed), persist each to PostgreSQL,
    and return the list of job dicts (title, company, location, url, description, source).
    """
    if profile.get("error"):
        raise ValueError("Profile contains error; cannot search jobs.")

    # Keys are loaded for consistency with project .env (vision uses OpenAI only).
    _ = os.getenv("ANTHROPIC_API_KEY")
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY is not set; vision fallback will be unavailable.")

    role = _first_role(profile)
    location = _first_location(profile)
    url = _indeed_search_url(role, location)
    logger.info("Indeed search: %s", url)

    jobs: List[Dict[str, Any]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=_playwright_headless())
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            try:
                await _delay_action()
                await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                await _delay_action()
                await _try_dismiss_consent(page)

                try:
                    await page.wait_for_selector(
                        "div.job_seen_beacon, li.resultContent, div#mosaic-provider-jobcards a",
                        timeout=45_000,
                    )
                except PlaywrightTimeoutError:
                    logger.warning("Timeout waiting for job list selectors.")

                await _delay_action()
                for _ in range(4):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await _delay_action()

                jobs = await _extract_jobs_dom(page)

                if len(jobs) < MIN_DOM_RESULTS:
                    logger.info(
                        "DOM returned %s jobs (< %s); trying GPT-4o vision fallback.",
                        len(jobs),
                        MIN_DOM_RESULTS,
                    )
                    vision_jobs = await _extract_jobs_vision(page)
                    by_url = {j["url"]: j for j in jobs}
                    for vj in vision_jobs:
                        by_url.setdefault(vj["url"], vj)
                    jobs = list(by_url.values())
            finally:
                await _delay_action()
                await context.close()
                await browser.close()
    except PlaywrightError as exc:
        logger.exception("Playwright error: %s", exc)
        raise RuntimeError(f"Browser automation failed: {exc!s}") from exc

    saved: List[Dict[str, Any]] = []
    for job in jobs:
        try:
            jid = await asyncio.to_thread(tracker_db.save_job, job)
            job_with_id = {**job, "id": jid}
            saved.append(job_with_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save job %s: %s", job.get("url"), exc)

    return saved


async def search_jobs(query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Backward-compatible entry: builds a minimal profile from query and optional location."""
    loc = "United States"
    if filters and isinstance(filters.get("location"), str) and filters["location"].strip():
        loc = filters["location"].strip()
    profile: Dict[str, Any] = {
        "target_roles": [query],
        "preferred_locations": [loc],
        "location": loc,
    }
    return await find_jobs(profile)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _demo() -> None:
        sample_profile: Dict[str, Any] = {
            "name": "Demo User",
            "email": "demo@example.com",
            "target_roles": ["AI Engineer"],
            "preferred_locations": ["Boston"],
            "location": "Boston, MA",
            "skills": ["Python", "PyTorch"],
            "experience_years": 3,
            "seniority": "mid",
            "education": [],
            "visa_status": "citizen",
            "salary_min": 0,
            "industries": [],
            "summary": "Demo profile for Indeed search.",
            "phone": "",
        }
        found = await find_jobs(sample_profile)
        print(f"Found {len(found)} jobs (saved to DB where possible).")
        for j in found:
            print(f"- {j.get('title')} @ {j.get('company')} (id={j.get('id')})")

    asyncio.run(_demo())
