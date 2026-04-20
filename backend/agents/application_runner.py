"""End-to-end application form flow for a single job (fill only; no submit)."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

load_dotenv(_BACKEND_ROOT / ".env", override=True)

from agents.apply_navigator import IndeedAuthBlockedError, prepare_application_page  # noqa: E402
from agents.cover_letter import generate_cover_letter  # noqa: E402
from agents.form_filler import fill_application_fields  # noqa: E402
from agents.form_reader import read_form_fields  # noqa: E402
from tracker.db import get_job_by_id, get_latest_candidate_profile, insert_application  # noqa: E402

logger = logging.getLogger(__name__)

_SCREENSHOT_DIR = _BACKEND_ROOT / "var" / "screenshots"


async def run_application_flow(job_id: int, profile: Dict[str, Any]) -> None:
    """
    Fetch job, generate cover letter, open application URL, read and fill the form,
    capture screenshots, persist ``applications`` row with status ``filled`` (not submitted).

    Only runs when job ``recommendation`` is ``apply`` or ``review``.
    """
    job_row = get_job_by_id(job_id)
    if not job_row:
        print(f"No job found with id={job_id}")
        return

    rec = (job_row.get("recommendation") or "").strip().lower()
    if rec not in ("apply", "review"):
        print(
            f"Skipping job_id={job_id}: recommendation is {job_row.get('recommendation')!r} "
            f"(only 'apply' or 'review' are processed)."
        )
        return

    job = {
        "id": job_row["id"],
        "title": job_row.get("title") or "",
        "company": job_row.get("company") or "",
        "description": (job_row.get("description") or "") or "",
        "location": job_row.get("location") or "",
        "url": (job_row.get("url") or "").strip(),
    }
    if not job["url"]:
        print(f"Job {job_id} has no URL; aborting.")
        return

    print(f"--- Job: {job['title']} @ {job['company']} ---")
    print("Generating cover letter...")
    cover = await generate_cover_letter(job, profile)
    if cover.startswith("Unable to generate"):
        print(f"Cover letter issue: {cover[:200]}...")
    else:
        print(f"Cover letter ({len(cover.split())} words) ready.")

    fill_summary: Dict[str, Any] = {}
    verify_shot = ""
    final_shot = ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page: Page = await context.new_page()
        try:
            print(f"Opening {job['url'][:80]}...")
            await page.goto(job["url"], wait_until="domcontentloaded", timeout=120_000)
            await asyncio.sleep(3.0)

            print("Preparing page (apply / consent if needed)...")
            page = await prepare_application_page(page, job_id=job_id, cover_letter=cover)
            print(f"Active URL: {(page.url or '')[:100]}...")

            print("Reading form fields (GPT-4o Vision + DOM fallback)...")
            fields = await read_form_fields(page)
            print(f"Detected {len(fields)} field(s).")

            print("Filling fields...")
            fill_summary = await fill_application_fields(page, fields, profile, cover)
            verify_shot = str(fill_summary.get("screenshot_path", ""))

            _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            final_path = _SCREENSHOT_DIR / f"app_prefinal_job{job_id}_{stamp}.png"
            await page.screenshot(path=str(final_path), full_page=True)
            final_shot = str(final_path)
            print(f"Pre-submit screenshot saved: {final_shot}")

            # TODO: uncomment to enable auto-submit
            # await page.locator('button[type="submit"], input[type="submit"]').first.click()

        finally:
            await context.close()
            await browser.close()

    err_parts = list(fill_summary.get("errors") or [])
    err_blob = "\n".join(err_parts)[:7500] if err_parts else None
    meta = f"verify_screenshot={verify_shot}; final_screenshot={final_shot}"
    combined = f"{meta}\n{err_blob}" if err_blob else meta

    app_id = insert_application(
        job_id=job_id,
        status="filled",
        cover_letter=cover,
        form_filled=True,
        error_message=combined[:8000] if combined else None,
    )

    print()
    print("=== Summary ===")
    print(f"application_id: {app_id}")
    print(f"fields_filled: {fill_summary.get('fields_filled', 0)}")
    print(f"fields_skipped: {fill_summary.get('fields_skipped', 0)}")
    print(f"verification screenshot: {verify_shot}")
    print(f"final screenshot: {final_shot}")
    if fill_summary.get("errors"):
        print("fill errors (first 5):")
        for e in (fill_summary["errors"])[:5]:
            print(f"  - {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _jid = 1
    if len(sys.argv) > 1:
        try:
            _jid = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python -m agents.application_runner [job_id]\nInvalid job_id: {sys.argv[1]!r}")
            sys.exit(1)

    async def _main() -> None:
        profile = get_latest_candidate_profile()
        if not profile:
            print("No candidate in database. Run POST /start or insert a candidate first.")
            return
        try:
            await run_application_flow(_jid, profile)
        except IndeedAuthBlockedError as exc:
            print(f"Indeed auth wall (recorded as auth_blocked): {exc}")

    asyncio.run(_main())
