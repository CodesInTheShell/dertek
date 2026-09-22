from __future__ import annotations

import os

from dertek.events import EventSink
from dertek.router.base import DecisionEngine
from dertek.router.fallback import FallbackRouter
from dertek.router.heuristic import HeuristicRouter
from dertek.router.jev import TypeSafeJevRouter


def build_router(events: EventSink | None = None) -> DecisionEngine:
    fallback = HeuristicRouter()
    if not os.getenv("TYPESAFE_API_KEY"):
        return fallback
    return FallbackRouter(TypeSafeJevRouter(), fallback, events=events)
