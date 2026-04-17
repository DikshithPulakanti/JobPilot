"""Playwright-based browser agent for job discovery."""

from typing import Any, Dict, List, Optional


async def search_jobs(query: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Run browser automation to find job postings."""
    raise NotImplementedError("Implement Playwright job search flows.")
