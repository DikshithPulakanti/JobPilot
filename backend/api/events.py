"""Server-Sent Events hub for dashboard live feed."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["events"])


class EventHub:
    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._queues.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            if queue in self._queues:
                self._queues.remove(queue)

    async def publish(self, event: dict[str, Any]) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        async with self._lock:
            targets = list(self._queues)
        for queue in targets:
            await queue.put(payload)


event_hub = EventHub()


@router.get("/events")
async def stream_events(request: Request) -> EventSourceResponse:
    queue = await event_hub.subscribe()

    async def event_generator():
        try:
            await event_hub.publish(
                {
                    "action": "stream_connected",
                    "company": None,
                    "title": None,
                    "details": {},
                    "status": "info",
                }
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "jobpilot", "data": json.dumps(message)}
        finally:
            await event_hub.unsubscribe(queue)

    return EventSourceResponse(event_generator())


__all__ = ["router", "event_hub", "EventHub"]
