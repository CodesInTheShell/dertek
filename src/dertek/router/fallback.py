from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from dertek.events import AgentEvent, EventSink, EventType, NullEventSink
from dertek.router.base import DecisionEngine
from dertek.router.models import (
    CheckpointDecision,
    CheckpointState,
    IntakeDecision,
    VerificationDecision,
    VerificationState,
)

T = TypeVar("T")


class FallbackRouter:
    def __init__(
        self, primary: DecisionEngine, fallback: DecisionEngine, events: EventSink | None = None
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.events = events or NullEventSink()

    async def _run(self, phase: str, primary: Callable[[], Awaitable[T]], fallback: Callable[[], Awaitable[T]]) -> T:
        try:
            return await primary()
        except Exception as exc:
            self.events.emit(AgentEvent(EventType.INFO, f"TypeSafe {phase} unavailable; using heuristic fallback", {"error": str(exc), "phase": phase}))
            result = await fallback()
            if hasattr(result, "source"):
                result.source = "heuristic-after-jev-error"
            return result

    async def route(self, prompt: str, workspace: Path) -> IntakeDecision:
        return await self.intake(prompt, workspace)

    async def intake(self, prompt: str, workspace: Path) -> IntakeDecision:
        return await self._run("intake", lambda: self.primary.intake(prompt, workspace), lambda: self.fallback.intake(prompt, workspace))

    async def checkpoint(self, state: CheckpointState) -> CheckpointDecision:
        return await self._run("checkpoint", lambda: self.primary.checkpoint(state), lambda: self.fallback.checkpoint(state))

    async def verify(self, state: VerificationState, candidate_answer: str) -> VerificationDecision:
        return await self._run("verification", lambda: self.primary.verify(state, candidate_answer), lambda: self.fallback.verify(state, candidate_answer))
