"""2Captcha integration for solving CAPTCHAs during automation."""

import os
from typing import Any


def get_solver() -> Any:
    """Return a configured 2Captcha client when TWOCAPTCHA_API_KEY is set."""
    from twocaptcha import TwoCaptcha

    api_key = os.getenv("TWOCAPTCHA_API_KEY")
    if not api_key:
        raise RuntimeError("TWOCAPTCHA_API_KEY is not configured.")
    return TwoCaptcha(api_key)


async def solve_recaptcha(site_key: str, page_url: str) -> str:
    """Submit reCAPTCHA to 2Captcha and return the solution token."""
    solver = get_solver()
    result = solver.recaptcha(sitekey=site_key, url=page_url)
    return result.get("code", "")
