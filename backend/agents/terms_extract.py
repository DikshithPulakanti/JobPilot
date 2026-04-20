"""Best-effort extraction of legal / terms text from application pages (Indeed / ATS iframes)."""

from __future__ import annotations

from playwright.async_api import Page


async def extract_terms_snippet_from_page(page: Page) -> str:
    """
    Collect visible snippets that look like policies, EEO statements, or terms.

    This is heuristic: real employers use many layouts; we merge whatever matches.
    """
    selectors = (
        '[class*="legal" i]',
        '[class*="terms" i]',
        '[class*="policy" i]',
        '[id*="terms" i]',
        '[data-testid*="terms" i]',
        "section[aria-label*='legal' i]",
    )
    chunks: list[str] = []
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            txt = await loc.inner_text(timeout=4000)
            t = (txt or "").strip()
            if len(t) > 120:
                chunks.append(t[:8000])
        except Exception:
            continue

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            low = (await frame.content()).lower()
        except Exception:
            continue
        if not any(
            k in low
            for k in (
                "equal opportunity",
                "eeo",
                "privacy",
                "at-will",
                "at will",
                "background check",
                "terms of use",
            )
        ):
            continue
        try:
            body = frame.locator("body").first
            if await body.count() == 0:
                continue
            txt = await body.inner_text(timeout=4000)
            t = (txt or "").strip()
            if len(t) > 200:
                chunks.append(t[:8000])
        except Exception:
            continue

    # De-dupe while keeping order
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        key = c[:200]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)

    return "\n\n---\n\n".join(out)[:24000]
