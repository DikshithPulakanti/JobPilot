"""Exception types treated as transient for orchestrator retries."""

from __future__ import annotations

import asyncio
from typing import Tuple, Type

_types: list[Type[BaseException]] = []

try:
    from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError

    _types.append(PlaywrightTimeoutError)
except ImportError:  # pragma: no cover
    pass

_types.append(asyncio.TimeoutError)

try:
    from httpx import RemoteProtocolError

    _types.append(RemoteProtocolError)
except ImportError:  # pragma: no cover
    pass

try:
    from anthropic import APIConnectionError as AnthropicAPIConnectionError

    _types.append(AnthropicAPIConnectionError)
except ImportError:  # pragma: no cover
    pass

try:
    from openai import APIConnectionError as OpenAIAPIConnectionError

    _types.append(OpenAIAPIConnectionError)
except ImportError:  # pragma: no cover
    pass

RETRYABLE_EXCEPTION_TYPES: Tuple[Type[BaseException], ...] = tuple(_types)


def is_retryable_exception(exc: BaseException) -> bool:
    """Return True if ``exc`` should trigger retry_with_backoff (transient)."""
    return isinstance(exc, RETRYABLE_EXCEPTION_TYPES)
