"""Playwright agent for filling job application forms from reader output."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SCREENSHOT_DIR = _BACKEND_ROOT / "var" / "screenshots"


def field_mapper(
    what_to_fill: str,
    profile: Dict[str, Any],
    cover_letter: str,
    *,
    label: str = "",
    placeholder: str = "",
) -> Optional[Any]:
    """
    Map ``what_to_fill`` (from form reader) to a value suitable for Playwright.

    ``label`` / ``placeholder`` are used when the reader returns ``custom field`` or DOM fallback
    text so we can still match email, name, etc.

    Returns ``None`` to skip the field (unrecognized, or resume upload handled separately).
    For checkboxes, returns ``True`` or ``False``.
    """
    key = (what_to_fill or "").strip().lower()
    hint = f"{what_to_fill} {label} {placeholder}".strip().lower()

    if (
        key == "resume file upload"
        or ("resume" in key and "upload" in key)
        or ("cv" in key and "upload" in key)
        or ("portfolio" in key and "upload" in key)
        or ("resume" in hint and "upload" in hint)
        or ("cv" in hint and "upload" in hint)
    ):
        return None

    if key == "candidate full name" or ("full name" in key and "company" not in key):
        return str(profile.get("name", "") or "").strip() or None
    if key == "email address" or key == "email" or ("email" in key and "@" not in key):
        return str(profile.get("email", "") or "").strip() or None
    if key == "phone number" or "phone" in key or "mobile" in key:
        p = str(profile.get("phone", "") or "").strip()
        return p if p else "617-555-0100"
    if key == "years of experience" or ("experience" in key and "year" in key):
        return str(profile.get("experience_years", ""))
    if key == "cover letter text" or ("cover letter" in key and "upload" not in key):
        return cover_letter or ""
    if key == "linkedin url" or "linkedin" in key:
        slug = str(profile.get("name", "candidate")).lower().replace(" ", "-")
        return f"https://linkedin.com/in/{slug}"
    if key == "github url" or "github" in key:
        slug = str(profile.get("name", "candidate")).lower().replace(" ", "-")
        return f"https://github.com/{slug}"
    if key == "work authorization status" or "visa" in key or "authorization" in key or "eligible" in key:
        v = str(profile.get("visa_status", "other") or "other").lower()
        visa_map = {
            "opt": "Authorized to work, OPT",
            "h1b": "H1B visa holder",
            "citizen": "US Citizen",
            "greencard": "Permanent Resident",
            "green_card": "Permanent Resident",
            "other": "Authorized to work in the US",
        }
        return visa_map.get(v, "Authorized to work in the US")
    if key == "salary expectation" or ("salary" in key and "expect" in key) or "compensation" in key:
        return str(profile.get("salary_min", 90000))

    if "name" in key and "company" not in key:
        return str(profile.get("name", "") or "").strip() or None
    if "email" in key:
        return str(profile.get("email", "") or "").strip() or None

    # Hints from Vision/DOM labels when ``what_to_fill`` is generic
    if "email" in hint and "subject" not in hint:
        return str(profile.get("email", "") or "").strip() or None
    if "phone" in hint or "tel" in hint or "mobile" in hint:
        p = str(profile.get("phone", "") or "").strip()
        return p if p else "617-555-0100"
    if ("full name" in hint or "first name" in hint or "last name" in hint) and "company" not in hint:
        return str(profile.get("name", "") or "").strip() or None
    if "name" in hint and "company" not in hint and "user name" not in hint and "username" not in hint:
        if any(x in hint for x in ("your name", "candidate", "applicant", "full name")):
            return str(profile.get("name", "") or "").strip() or None
    if "linkedin" in hint:
        slug = str(profile.get("name", "candidate")).lower().replace(" ", "-")
        return f"https://linkedin.com/in/{slug}"
    if "github" in hint:
        slug = str(profile.get("name", "candidate")).lower().replace(" ", "-")
        return f"https://github.com/{slug}"
    if ("cover" in hint or "letter" in hint or "message" in hint) and "upload" not in hint:
        return cover_letter or ""
    if "year" in hint and "experience" in hint:
        return str(profile.get("experience_years", ""))
    if "salary" in hint or "compensation" in hint or "pay expectation" in hint:
        return str(profile.get("salary_min", 90000))
    if "authoriz" in hint or "visa" in hint or "eligible" in hint or "legally" in hint:
        v = str(profile.get("visa_status", "other") or "other").lower()
        visa_map = {
            "opt": "Authorized to work, OPT",
            "h1b": "H1B visa holder",
            "citizen": "US Citizen",
            "greencard": "Permanent Resident",
            "green_card": "Permanent Resident",
            "other": "Authorized to work in the US",
        }
        return visa_map.get(v, "Authorized to work in the US")

    return None


async def _delay_between_fields() -> None:
    await asyncio.sleep(random.uniform(0.5, 1.0))


def _frames_ordered(page: Page, selector: str) -> List[Frame]:
    """
    Order frames for lookup.

    Child frames first when the selector likely targets an embedded apply form
    (Indeed SmartApply ``ifl-`` ids, or generic ``input``/``textarea``/``select`` queries).
    """
    frames: List[Frame] = list(page.frames)
    if len(frames) <= 1:
        return frames
    sl = (selector or "").lower()
    if "ifl-" in sl or "indeed" in sl:
        return [f for f in frames if f != page.main_frame] + [page.main_frame]
    if any(
        tok in sl
        for tok in (
            "input[",
            "textarea",
            "select",
            "button[type=",
            '[contenteditable="true"]',
        )
    ):
        return [f for f in frames if f != page.main_frame] + [page.main_frame]
    return frames


async def _locator_in_all_frames(page: Page, selector: str) -> Optional[Locator]:
    """
    Resolve ``selector`` in the main document or any attached iframe.

    Indeed SmartApply and similar embeds use child frames; IDs like ``ifl-InputFormField-*``
    only exist inside those frames, so ``page.locator(...)`` on the root page misses them.
    """
    sel = (selector or "").strip()
    if not sel:
        return None

    for attempt in range(6):
        frames = _frames_ordered(page, sel)
        for frame in frames:
            loc = frame.locator(sel).first
            try:
                if await loc.count() == 0:
                    continue
                if attempt < 5:
                    if await loc.is_visible(timeout=2500):
                        return loc
                else:
                    return loc
            except Exception:  # noqa: BLE001
                continue
        if attempt < 5:
            await asyncio.sleep(0.85)

    return None


def _semantic_fallback_selectors(field: Dict[str, Any]) -> List[str]:
    """
    Extra CSS selectors when Vision returns a generic id (e.g. ``#email``) that is not in the DOM.

    Ordered roughly most-specific first.
    """
    ftype = str(field.get("field_type", "text")).lower()
    wtf = str(field.get("what_to_fill", "")).lower()
    lab = str(field.get("label", "")).lower()
    ph = str(field.get("placeholder", "")).lower()
    blob = f"{ftype} {wtf} {lab} {ph}"

    seen: set[str] = set()
    out: List[str] = []

    def add(s: str) -> None:
        t = s.strip()
        if not t or t in seen:
            return
        seen.add(t)
        out.append(t)

    if ftype == "email" or "email" in wtf or "e-mail" in blob:
        add('input[type="email"]')
        add('input[autocomplete="email"]')
        add('input[name="email"]')
        add('input[name="Email"]')
        add('input[name="candidateEmail"]')
        add('input[name*="email"]')
        add('input[id*="email"]')
        add('input[id*="Email"]')
        add('input[data-testid*="email"]')
        add('[data-testid*="email"] input')

    if ftype == "phone" or "phone" in wtf or "tel" in blob or "mobile" in blob:
        add('input[type="tel"]')
        add('input[autocomplete="tel"]')
        add('input[name*="phone"]')
        add('input[id*="phone"]')

    if (
        ftype == "textarea"
        or "cover" in wtf
        or "letter" in wtf
        or "cover" in blob
        or "message" in blob
    ):
        add('textarea[name*="cover"]')
        add('textarea[name*="letter"]')
        add('textarea[id*="cover"]')
        add('textarea[id*="letter"]')
        add('textarea[aria-label*="Cover"]')
        add('textarea[aria-label*="Letter"]')

    if "name" in wtf or "full name" in blob or ("first" in lab and "last" in lab):
        add('input[name*="firstName"]')
        add('input[name*="lastName"]')
        add('input[name="name"]')
        add('input[autocomplete="name"]')
        add('input[id*="name"]')

    if "linkedin" in wtf or "linkedin" in blob:
        add('input[name*="linkedin"]')
        add('input[id*="linkedin"]')
    if "github" in wtf or "github" in blob:
        add('input[name*="github"]')
        add('input[id*="github"]')

    if "experience" in wtf or "year" in blob:
        add('input[name*="experience"]')
        add('input[id*="experience"]')

    if "salary" in wtf or "compensation" in blob:
        add('input[name*="salary"]')
        add('input[id*="salary"]')

    if "visa" in wtf or "authoriz" in blob or "eligible" in blob:
        add('select[name*="visa"]')
        add('select[name*="authorized"]')
        add('input[name*="authorized"]')

    return out


async def _get_by_label_in_frames(page: Page, label: str) -> Optional[Locator]:
    label = str(label or "").strip()
    if len(label) < 2:
        return None
    frames = [f for f in page.frames if f != page.main_frame] + [page.main_frame]
    for frame in frames:
        try:
            loc = frame.get_by_label(label, exact=False).first
            if await loc.count() == 0:
                continue
            if await loc.is_visible(timeout=2000):
                return loc
        except Exception:  # noqa: BLE001
            continue
    return None


async def _get_by_placeholder_in_frames(page: Page, placeholder: str) -> Optional[Locator]:
    placeholder = str(placeholder or "").strip()
    if len(placeholder) < 2:
        return None
    frames = [f for f in page.frames if f != page.main_frame] + [page.main_frame]
    for frame in frames:
        try:
            loc = frame.get_by_placeholder(placeholder, exact=False).first
            if await loc.count() == 0:
                continue
            if await loc.is_visible(timeout=2000):
                return loc
        except Exception:  # noqa: BLE001
            continue
    return None


async def _resolve_field_locator(page: Page, field: Dict[str, Any]) -> Optional[Locator]:
    """Primary Vision selector, semantic CSS fallbacks, then label / placeholder."""
    primary = str(field.get("css_selector") or "").strip()
    ordered: List[str] = []
    if primary:
        ordered.append(primary)
    for fb in _semantic_fallback_selectors(field):
        if fb not in ordered:
            ordered.append(fb)

    for s in ordered:
        loc = await _locator_in_all_frames(page, s)
        if loc is not None:
            if s != primary:
                logger.info("Resolved field using fallback selector %r (primary was %r)", s, primary)
            return loc

    loc = await _get_by_label_in_frames(page, str(field.get("label") or ""))
    if loc is not None:
        logger.info("Resolved field using get_by_label(%r)", field.get("label"))
        return loc

    loc = await _get_by_placeholder_in_frames(page, str(field.get("placeholder") or ""))
    if loc is not None:
        logger.info("Resolved field using get_by_placeholder(%r)", field.get("placeholder"))
        return loc

    return None


async def fill_application_fields(
    page: Page,
    fields: List[Dict[str, Any]],
    profile: Dict[str, Any],
    cover_letter: str,
) -> Dict[str, Any]:
    """
    Fill visible form fields using Playwright. File uploads are skipped and logged.

    Returns dict with fields_filled, fields_skipped, screenshot_path, errors.
    """
    errors: List[str] = []
    filled = 0
    skipped = 0

    for field in fields:
        await _delay_between_fields()
        sel = str(field.get("css_selector", "")).strip()
        ftype = str(field.get("field_type", "text")).lower()
        what = str(field.get("what_to_fill", ""))
        flabel = str(field.get("label", "") or "")
        fph = str(field.get("placeholder", "") or "")

        if not sel:
            skipped += 1
            errors.append("Empty css_selector; skipped.")
            continue

        try:
            loc = await _resolve_field_locator(page, field)
            if loc is None:
                skipped += 1
                errors.append(
                    f"No element for selector {sel!r} "
                    f"(iframes + semantic fallbacks + label/placeholder; "
                    f"what_to_fill={what!r} label={flabel!r})"
                )
                continue
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            errors.append(f"Locator error {sel!r}: {exc!s}")
            continue

        mapped = field_mapper(what, profile, cover_letter, label=flabel, placeholder=fph)

        try:
            if ftype == "file":
                skipped += 1
                logger.info("Skipping file upload field: %s (%s)", what, sel)
                errors.append(f"Skipped file field: {what} ({sel})")
                continue

            if ftype == "checkbox":
                if mapped is None:
                    skipped += 1
                    continue
                truthy = mapped is True or (isinstance(mapped, str) and mapped.lower() in ("true", "yes", "1"))
                if truthy:
                    await loc.check()
                else:
                    await loc.uncheck()
                filled += 1
                continue

            if ftype == "radio":
                await loc.click()
                filled += 1
                continue

            if ftype == "dropdown":
                if mapped is None:
                    skipped += 1
                    continue
                val = str(mapped)
                try:
                    await loc.select_option(label=val, timeout=5000)
                except PlaywrightError:
                    await loc.select_option(value=val, timeout=5000)
                filled += 1
                continue

            if mapped is None:
                skipped += 1
                logger.debug("Unrecognized or empty mapping for %s; skip.", what)
                continue

            val = str(mapped)
            if ftype in ("text", "email", "phone", "textarea"):
                await loc.fill(val, timeout=15_000)
                filled += 1
                continue

            await loc.fill(val, timeout=15_000)
            filled += 1

        except Exception as exc:  # noqa: BLE001
            msg = f"Failed {ftype} {sel!r} ({what}): {exc!s}"
            logger.warning(msg)
            errors.append(msg)
            skipped += 1

    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    shot_path = _SCREENSHOT_DIR / f"form_verify_{stamp}.png"
    try:
        await page.screenshot(path=str(shot_path), full_page=True)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Verification screenshot failed: {exc!s}")
        shot_path = shot_path.parent / "form_verify_failed.png"
        try:
            await page.screenshot(path=str(shot_path), full_page=True)
        except Exception:
            shot_path = Path("")

    return {
        "fields_filled": filled,
        "fields_skipped": skipped,
        "screenshot_path": str(shot_path) if shot_path else "",
        "errors": errors,
    }


async def fill_application_form(url: str, field_values: dict[str, Any]) -> None:
    """Legacy placeholder — use :func:`fill_application_fields` with a ``Page`` instance."""
    raise NotImplementedError("Use fill_application_fields(page, fields, profile, cover_letter).")
