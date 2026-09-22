from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TaskRoute(StrEnum):
    CHAT = "chat"
    CODE = "code"
    DEBUG = "debug"
    SEARCH = "search"
    COMMAND = "command"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(slots=True)
class RouteDecision:
    route: TaskRoute
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    source: str = "unknown"


@dataclass(slots=True)
class RouteResolution:
    route: TaskRoute | None
    confidence: float
    band: ConfidenceBand
    apply_as_constraint: bool
