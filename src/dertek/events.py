from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    ROUTE = "route"
    DECISION_STARTED = "decision_started"
    DECISION_FINISHED = "decision_finished"
    MODEL_ESCALATED = "model_escalated"
    MODEL_STARTED = "model_started"
    MODEL_FINISHED = "model_finished"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_DENIED = "tool_denied"
    APPROVAL_REQUIRED = "approval_required"
    INFO = "info"
    ERROR = "error"


@dataclass(slots=True)
class AgentEvent:
    type: EventType
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None
    run_id: str | None = None
    sequence: int | None = None


class EventSink(Protocol):
    def emit(self, event: AgentEvent) -> None: ...


class NullEventSink:
    def emit(self, event: AgentEvent) -> None:
        del event
