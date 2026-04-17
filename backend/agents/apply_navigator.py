"""Open job-board apply flows so form_reader sees real application fields."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional, Protocol

from playwright.async_api import Locator, Page

logger = logging.getLogger(__name__)


class _LocatorRoot(Protocol):
    """Anything we can chain ``.locator`` / ``.get_by_role`` from."""

    def locator(self, selector: str) -> Locator: ...
    def get_by_role(self, role: str, **kwargs: object) -> Locator: ...


async def dismiss_common_overlays(page: Page) -> None:
    """Close cookie / consent banners that block clicks."""
    selectors = (
        "#onetrust-accept-btn-handler",
        'button:has-text("Accept all cookies")',
        'button:has-text("Accept All")',
        'button[aria-label*="Accept"]',
        'button:has-text("Got it")',
        'button:has-text("Dismiss")',
    )
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.is_visible(timeout=1200):
                await loc.click(timeout=3000)
                await asyncio.sleep(0.4)
                logger.info("Dismissed overlay: %s", sel)
                return
        except Exception:  # noqa: BLE001
            continue


async def _indeed_job_container(page: Page) -> _LocatorRoot:
    """Prefer the job detail column so we do not hit global nav / footer."""
    for sel in (
        '[data-testid="jobsearch-ViewJobLayout-container"]',
        '[data-testid="jobsearch-BodySearchContainer"]',
        "#jobsearch-ViewjobPaneWrapper",
        "#jobsearch-ViewJobPane",
        "div.jobsearch-JobComponent",
    ):
        loc = page.locator(sel).first
        try:
            if await loc.count() and await loc.is_visible(timeout=2500):
                return loc
        except Exception:  # noqa: BLE001
            continue
    return page


def _indeed_apply_roots(page: Page, job_container: _LocatorRoot) -> List[_LocatorRoot]:
    """Job panel first, then full page, then non-main frames that may host the apply UI."""
    roots: List[_LocatorRoot] = [job_container, page]
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        u = (fr.url or "").lower()
        if not u or u == "about:blank":
            continue
        if "indeed.com" in u or "apply" in u or "smartapply" in u:
            roots.append(fr)
    # De-duplicate preserving order
    seen: set[int] = set()
    out: List[_LocatorRoot] = []
    for r in roots:
        i = id(r)
        if i in seen:
            continue
        seen.add(i)
        out.append(r)
    return out


async def _scroll_apply_into_view(page: Page) -> None:
    try:
        await page.evaluate(
            "() => { window.scrollTo(0, Math.min(700, Math.max(0, document.body.scrollHeight * 0.12))); }"
        )
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(0.4)


async def _click_apply_target(page: Page, loc: Locator) -> Optional[Page]:
    """
    Click a resolved apply control; return a new ``Page`` if a tab opened, else ``page``
    for same-document flows, or ``None`` if the click failed.
    """
    try:
        await loc.scroll_into_view_if_needed(timeout=8000)
    except Exception:  # noqa: BLE001
        pass
    n_before = len(page.context.pages)
    try:
        await loc.click(timeout=25_000, force=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Apply click failed: %s", exc)
        try:
            await loc.click(timeout=15_000, force=True)
        except Exception as exc2:  # noqa: BLE001
            logger.debug("Apply force-click failed: %s", exc2)
            return None

    await asyncio.sleep(1.2)
    pages = page.context.pages
    if len(pages) > n_before:
        newp = pages[-1]
        try:
            await newp.wait_for_load_state("domcontentloaded", timeout=90_000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("New apply tab load: %s", exc)
        await asyncio.sleep(2.0)
        logger.info("Apply opened a new tab: %s", (newp.url or "")[:140])
        return newp

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=35_000)
    except Exception:
        pass
    await asyncio.sleep(2.0)
    logger.info("Apply clicked (same window). URL=%s", (page.url or "")[:140])
    return page


def _indeed_apply_locators(root: _LocatorRoot) -> List[Locator]:
    """Ordered locators for Indeed apply (CSS + text + role)."""
    locators: List[Locator] = []

    css = (
        "a#indeedApplyButton",
        "button#indeedApplyButton",
        "a.indeed-apply-button",
        "button.indeed-apply-button",
        '[class*="indeedApply"]',
        '[class*="IndeedApplyButton"]',
        'a[href*="indeedapply"]',
        'a[href*="smartapply"]',
        'a[href*="/apply?"]',
        'a[href*="apply.indeed.com"]',
        'button[data-testid="indeedApplyButton"]',
        'a[data-testid="indeedApplyButton"]',
        '[data-testid="indeed-ApplyButton"]',
        '[data-testid="apply-button"] a',
        '[data-testid="apply-button"]',
    )
    for sel in css:
        locators.append(root.locator(sel))

    text_res = (
        re.compile(r"apply\s+on\s+(the\s+)?company", re.I),
        re.compile(r"apply\s+on\s+employer", re.I),
        re.compile(r"apply\s+with\s+your\s+indeed", re.I),
        re.compile(r"easily\s+apply", re.I),
        re.compile(r"continue\s+to\s+application", re.I),
        re.compile(r"apply\s+now", re.I),
        re.compile(r"^apply$", re.I),
    )
    for pat in text_res:
        locators.append(root.locator("a, button, [role='button']").filter(has_text=pat))

    role_patterns: tuple[tuple[str, str], ...] = (
        ("link", r"apply\s+on\s+(the\s+)?company"),
        ("link", r"apply\s+on\s+employer"),
        ("button", r"apply\s+on\s+(the\s+)?company"),
        ("button", r"apply\s+with\s+your\s+indeed"),
        ("button", r"easily\s+apply"),
        ("link", r"easily\s+apply"),
        ("button", r"apply\s*now"),
        ("link", r"apply\s*now"),
        ("button", r"^apply$"),
        ("link", r"^apply$"),
    )
    for role, pat in role_patterns:
        locators.append(root.get_by_role(role, name=re.compile(pat, re.I)))

    return locators


async def _indeed_try_roots(page: Page, roots: List[_LocatorRoot]) -> Optional[Page]:
    for root in roots:
        for loc in _indeed_apply_locators(root):
            try:
                if await loc.count() == 0:
                    continue
                first = loc.first
                if not await first.is_visible(timeout=2000):
                    continue
            except Exception:  # noqa: BLE001
                continue
            out = await _click_apply_target(page, first)
            if out is not None:
                return out
    return None


async def _indeed_open_apply(page: Page) -> Optional[Page]:
    """
    On Indeed job pages, click the primary Apply control and return the page that
    hosts the application (new tab/window if opened, else same page).
    """
    u = (page.url or "").lower()
    if "indeed.com" not in u:
        return None

    await dismiss_common_overlays(page)

    try:
        await page.wait_for_load_state("networkidle", timeout=12_000)
    except Exception:
        pass
    await asyncio.sleep(1.0)
    await _scroll_apply_into_view(page)

    job_container = await _indeed_job_container(page)
    roots = _indeed_apply_roots(page, job_container)
    result = await _indeed_try_roots(page, roots)
    if result is not None:
        return result

    logger.info("No Indeed Apply control found (external-only or layout change).")
    return None


async def prepare_application_page(page: Page) -> Page:
    """
    After landing on a job URL, try board-specific steps so application fields appear.

    Returns the ``Page`` to use for form reading (may be a new tab).
    """
    await dismiss_common_overlays(page)
    u = (page.url or "").lower()
    if "indeed.com" in u:
        opened = await _indeed_open_apply(page)
        if opened is not None:
            return opened
    return page
