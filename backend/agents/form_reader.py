"""GPT-4o Vision form field detection."""

from typing import Any


async def detect_form_fields(page_screenshot: bytes) -> list[dict[str, Any]]:
    """Analyze application form screenshots and return field metadata."""
    raise NotImplementedError("Call OpenAI vision API for field detection.")
