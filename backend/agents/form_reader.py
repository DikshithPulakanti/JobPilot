"""GPT-4o Vision form field detection from a live Playwright page."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import APIError, AsyncOpenAI, RateLimitError
from playwright.async_api import Page

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_ROOT / ".env", override=True)

logger = logging.getLogger(__name__)

ALLOWED_TYPES = frozenset(
    {"text", "email", "phone", "textarea", "dropdown", "checkbox", "radio", "file"}
)

VISION_PROMPT = """You are analyzing a screenshot of a job application web page.
Identify every distinct form field the applicant must complete (inputs, textareas, selects, file uploads, checkboxes, radio groups).

You MUST respond with one JSON object only (no markdown fences, no text before or after).
Use exactly this shape:
{"fields":[{"label":"...","field_type":"text","required":false,"css_selector":"#id_or_other","what_to_fill":"email address","placeholder":""}, ...]}

Each object in "fields" must have these keys:
- "label": exact visible label text near the field (or aria-label / placeholder if no separate label).
- "field_type": one of: "text", "email", "phone", "textarea", "dropdown", "checkbox", "radio", "file"
- "required": true or false (guess from asterisk or "required" hints).
- "css_selector": the best CSS selector Playwright can use (prefer #id, then [name="..."], avoid fragile nth-child).
- "what_to_fill": one of:
  "candidate full name", "email address", "phone number", "years of experience",
  "cover letter text", "resume file upload", "LinkedIn URL", "GitHub URL",
  "work authorization status", "salary expectation", or a short custom hint if none match.
- "placeholder": visible placeholder inside the field, or "".

Omit site-wide job search bars, cookie banners, login-only fields, and navigation search boxes unless they are clearly part of THIS job application.
If no application fields are visible, return {"fields":[]}."""


def _normalize_field_type(raw: str) -> str:
    t = (raw or "text").lower().strip()
    mapping = {
        "select": "dropdown",
        "drop-down": "dropdown",
        "listbox": "dropdown",
        "tel": "phone",
        "telephone": "phone",
        "number": "text",
        "url": "text",
    }
    t = mapping.get(t, t)
    return t if t in ALLOWED_TYPES else "text"


def _extract_json_array(text: str) -> Optional[List[Any]]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text, flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, list) else None


def _parse_vision_fields(raw: str) -> Optional[List[Any]]:
    """Parse model output: prefer ``{"fields": [...]}``, then bare JSON array."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text, flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Object with fields but trailing junk — try to locate "fields" array
        m = re.search(r'"fields"\s*:\s*\[', text)
        if m:
            start = m.end() - 1  # position of '['
            depth = 0
            end = -1
            for i, ch in enumerate(text[start:], start=start):
                if ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                try:
                    arr = json.loads(text[start:end])
                    return arr if isinstance(arr, list) else None
                except json.JSONDecodeError:
                    pass
        return _extract_json_array(text)

    if isinstance(data, dict):
        inner = data.get("fields")
        if isinstance(inner, list):
            return inner
        for k in ("form_fields", "items", "inputs"):
            inner = data.get(k)
            if isinstance(inner, list):
                return inner
        return None
    if isinstance(data, list):
        return data
    return None


def _normalize_field_item(obj: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    label = str(obj.get("label", "")).strip()
    sel = str(obj.get("css_selector", "")).strip()
    if not sel:
        return None
    wtf = str(obj.get("what_to_fill", "")).strip() or "custom field"
    return {
        "label": label or "(no label)",
        "field_type": _normalize_field_type(str(obj.get("field_type", "text"))),
        "required": bool(obj.get("required", False)),
        "css_selector": sel,
        "what_to_fill": wtf,
        "placeholder": str(obj.get("placeholder", "") or ""),
    }


def _is_likely_site_search_field(
    name: str,
    fid: str,
    ph: str,
    aria: str,
    inp_type: str,
) -> bool:
    """Filter Indeed/Glassdoor/etc. header search — not application fields."""
    n = name.lower()
    i = fid.lower()
    p = ph.lower()
    a = aria.lower()
    blob = f"{n} {i} {p} {a}"
    if inp_type in ("search", "button"):
        return True
    if "search" in a and ("job" in a or "keyword" in a or "location" in a or "what" in i or "where" in i):
        return True
    if n in ("q", "l") and ("keyword" in p or "job title" in p or "city" in p or "where" in p or "what" in p):
        return True
    if "text-input-what" in i or "text-input-where" in i:
        return True
    if "jobsearch" in i or "job-search" in i:
        return True
    if "keyword" in p and ("job" in p or "title" in p):
        return True
    if "where" in p and ("city" in p or "location" in p or "zip" in p):
        return True
    return False


def _infer_what_to_fill_from_text(label: str, ph: str, name: str, inp_type: str, ftype: str) -> str:
    """Heuristic mapping when Vision is unavailable."""
    blob = f"{label} {ph} {name}".lower()
    if "email" in blob or inp_type == "email":
        return "email address"
    if "phone" in blob or "tel" in blob or "mobile" in blob or ftype == "phone":
        return "phone number"
    if ("first" in blob and "last" in blob) or "full name" in blob or (
        "name" in blob and "company" not in blob and "user" not in blob
    ):
        return "candidate full name"
    if "linkedin" in blob:
        return "LinkedIn URL"
    if "github" in blob:
        return "GitHub URL"
    if "cover" in blob or "letter" in blob or "message" in blob or "additional" in blob:
        return "cover letter text"
    if "resume" in blob or "cv" in blob or "upload" in blob or ftype == "file":
        return "resume file upload"
    if "salary" in blob or "compensation" in blob or "pay" in blob:
        return "salary expectation"
    if "year" in blob and "experience" in blob:
        return "years of experience"
    if "authoriz" in blob or "visa" in blob or "eligible" in blob or "legally" in blob:
        return "work authorization status"
    return "custom field"


async def _fallback_dom_fields(page: Page) -> List[Dict[str, Any]]:
    """Heuristic scan of visible inputs when Vision JSON is unusable."""
    out: List[Dict[str, Any]] = []
    selectors = (
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="image"])',
        "textarea",
        "select",
    )
    seen: set[str] = set()

    for group in selectors:
        loc = page.locator(group)
        n = await loc.count()
        for i in range(n):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue
            except Exception:  # noqa: BLE001
                continue
            try:
                tag = await el.evaluate("e => e.tagName.toLowerCase()")
                inp_type = (await el.get_attribute("type") or "text").lower()
                name = (await el.get_attribute("name") or "").strip()
                fid = (await el.get_attribute("id") or "").strip()
                ph = (await el.get_attribute("placeholder") or "").strip()
                aria = (await el.get_attribute("aria-label") or "").strip()
            except Exception as exc:  # noqa: BLE001
                logger.debug("dom scan skip: %s", exc)
                continue

            if _is_likely_site_search_field(name, fid, ph, aria, inp_type):
                continue

            if not fid and not name:
                continue

            if fid:
                css = f"#{fid}"
            else:
                esc = name.replace('"', '\\"')
                if tag == "input":
                    css = f'input[name="{esc}"]'
                elif tag == "textarea":
                    css = f'textarea[name="{esc}"]'
                else:
                    css = f'select[name="{esc}"]'

            if css in seen:
                continue
            seen.add(css)

            label = aria or ph or name or f"{tag} field"
            if tag == "textarea":
                ftype = "textarea"
            elif tag == "select":
                ftype = "dropdown"
            elif inp_type in ("email",):
                ftype = "email"
            elif inp_type in ("tel", "phone"):
                ftype = "phone"
            elif inp_type == "checkbox":
                ftype = "checkbox"
            elif inp_type == "radio":
                ftype = "radio"
            elif inp_type == "file":
                ftype = "file"
            else:
                ftype = "text"

            wtf = _infer_what_to_fill_from_text(label, ph, name, inp_type, ftype)

            out.append(
                {
                    "label": label[:200],
                    "field_type": ftype,
                    "required": False,
                    "css_selector": css,
                    "what_to_fill": wtf,
                    "placeholder": ph,
                }
            )
    return out


async def read_form_fields(page: Page) -> List[Dict[str, Any]]:
    """
    Capture a full-page screenshot, ask GPT-4o Vision to list form fields, and return
    normalized field dicts. Falls back to DOM heuristics if the model response is not valid JSON.
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY missing; using DOM fallback only.")
        return await _fallback_dom_fields(page)

    png = await page.screenshot(full_page=True, type="png")
    b64 = base64.standard_b64encode(png).decode("ascii")

    client = AsyncOpenAI(api_key=api_key)
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": VISION_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[msg],
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
    except APIError as exc:
        err = str(exc).lower()
        if "response_format" in err or getattr(exc, "status_code", None) == 400:
            logger.warning("Retrying vision request without JSON mode: %s", exc)
            try:
                resp = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[msg],
                    max_tokens=4096,
                )
            except (RateLimitError, APIError) as exc2:
                logger.exception("OpenAI vision request failed: %s", exc2)
                return await _fallback_dom_fields(page)
        else:
            logger.exception("OpenAI vision request failed: %s", exc)
            return await _fallback_dom_fields(page)
    except Exception as exc:  # noqa: BLE001
        logger.exception("OpenAI vision error: %s", exc)
        return await _fallback_dom_fields(page)

    raw = (resp.choices[0].message.content or "").strip()
    parsed = _parse_vision_fields(raw)
    if parsed is None:
        snippet = raw[:280].replace("\n", " ")
        logger.warning("Vision returned invalid JSON; using DOM fallback. Snippet: %s", snippet)
        return await _fallback_dom_fields(page)

    fields: List[Dict[str, Any]] = []
    for item in parsed:
        norm = _normalize_field_item(item)
        if norm:
            fields.append(norm)

    if not fields:
        if len(parsed) == 0:
            logger.info("Vision reports no application fields on this page (empty fields array).")
            return []
        logger.warning(
            "Vision returned %d field entr(y/ies) but none had usable css_selector; using DOM fallback.",
            len(parsed),
        )
        return await _fallback_dom_fields(page)

    return fields


# Backward-compatible name
async def detect_form_fields(page: Page) -> List[Dict[str, Any]]:
    return await read_form_fields(page)
