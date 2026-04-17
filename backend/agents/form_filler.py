"""Playwright agent for filling application forms."""

from typing import Any


async def fill_application_form(url: str, field_values: dict[str, Any]) -> None:
    """Navigate and populate an external application form."""
    raise NotImplementedError("Implement Playwright form filling.")
