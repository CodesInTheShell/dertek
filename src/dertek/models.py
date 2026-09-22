from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    call_id: str
    tool_name: str
    output: str
    is_error: bool = False
    truncated: bool = False

    def as_provider_output(self) -> str:
        prefix = "ERROR: " if self.is_error else ""
        suffix = "\n[output truncated]" if self.truncated else ""
        return f"{prefix}{self.output}{suffix}"


@dataclass(slots=True)
class AgentRequest:
    model: str
    instructions: str
    input_items: str | list[dict[str, Any]]
    tools: list[dict[str, Any]]
    continuation_token: str | None = None
    reasoning_effort: str | None = None


@dataclass(slots=True)
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    continuation_token: str | None = None


@dataclass(slots=True)
class AgentRunResult:
    text: str
    steps: int
    route: str | None
    route_confidence: float | None
    model: str | None = None
    model_tier: str | None = None
    reasoning_effort: str | None = None
    model_transitions: list[dict[str, Any]] = field(default_factory=list)
    jev_call_count: int = 0
    verification_status: str | None = None
