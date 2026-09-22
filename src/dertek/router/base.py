from __future__ import annotations

from pathlib import Path
from typing import Protocol

from dertek.router.models import (
    CheckpointDecision,
    CheckpointState,
    IntakeDecision,
    VerificationDecision,
    VerificationState,
)


class DecisionEngine(Protocol):
    async def intake(self, prompt: str, workspace: Path) -> IntakeDecision: ...

    async def checkpoint(self, state: CheckpointState) -> CheckpointDecision: ...

    async def verify(
        self, state: VerificationState, candidate_answer: str
    ) -> VerificationDecision: ...


Router = DecisionEngine
