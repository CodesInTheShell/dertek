from __future__ import annotations

from pathlib import Path

from dertek.events import AgentEvent, EventSink, EventType, NullEventSink
from dertek.router.base import Router
from dertek.router.models import RouteDecision


class FallbackRouter:
    def __init__(self, primary: Router, fallback: Router, events: EventSink | None = None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.events = events or NullEventSink()

    async def route(self, prompt: str, workspace: Path) -> RouteDecision:
        try:
            return await self.primary.route(prompt, workspace)
        except Exception as exc:
            self.events.emit(
                AgentEvent(
                    EventType.INFO,
                    "TypeSafe router unavailable; using heuristic fallback",
                    {"error": str(exc)},
                )
            )
            return await self.fallback.route(prompt, workspace)
