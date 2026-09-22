from __future__ import annotations

import re
from pathlib import Path

from dertek.router.models import (
    CheckpointDecision,
    CheckpointState,
    Complexity,
    FailureCategory,
    IntakeDecision,
    ModelTier,
    NextAction,
    ProgressState,
    RiskLevel,
    TaskIntent,
    TaskRoute,
    TaskScope,
    ToolProfile,
    VerificationDecision,
    VerificationLevel,
    VerificationState,
    Workflow,
)


class HeuristicRouter:
    """Conservative availability fallback for all decision phases."""

    PATTERNS = [
        (TaskRoute.DEBUG, re.compile(r"\b(error|exception|traceback|failing|fails|bug|broken|debug|why.*fail)\b", re.I)),
        (TaskRoute.COMMAND, re.compile(r"\b(run|execute|build|test|pytest|npm test|uv run|git status)\b", re.I)),
        (TaskRoute.SEARCH, re.compile(r"\b(find|locate|where is|search|look for|which file)\b", re.I)),
        (TaskRoute.CODE, re.compile(r"\b(add|implement|create|change|modify|refactor|fix|edit|write|rename)\b", re.I)),
    ]

    async def route(self, prompt: str, workspace: Path) -> IntakeDecision:
        return await self.intake(prompt, workspace)

    async def intake(self, prompt: str, workspace: Path) -> IntakeDecision:
        del workspace
        route = TaskRoute.CHAT
        confidence = 0.60
        for candidate, pattern in self.PATTERNS:
            if pattern.search(prompt):
                route, confidence = candidate, 0.70
                break
        modifying = route == TaskRoute.CODE
        return IntakeDecision(
            route=route,
            confidence=confidence,
            source="heuristic",
            model_tier=ModelTier.LARGE,
            model_confidence=0.0,
            intent=TaskIntent.MODIFY if modifying else TaskIntent.INSPECT,
            complexity=Complexity.COMPLEX,
            risk=RiskLevel.LOW_MUTATION if modifying else RiskLevel.READ_ONLY,
            scope=TaskScope.UNKNOWN,
            workflow=Workflow.TEST_FIRST if route == TaskRoute.DEBUG else Workflow.INSPECT_FIRST,
            tool_profile=ToolProfile.UNRESTRICTED,
            verification=VerificationLevel.DIFF if modifying else VerificationLevel.NONE,
        )

    async def checkpoint(self, state: CheckpointState) -> CheckpointDecision:
        has_error = any(bool(item.get("is_error")) for item in state.tool_evidence)
        return CheckpointDecision(
            progress=ProgressState.BLOCKED if has_error else ProgressState.ON_TRACK,
            failure=FailureCategory.TOOL_ERROR if has_error else FailureCategory.NONE,
            next_action=NextAction.INSPECT if has_error else NextAction.CONTINUE,
            model_tier=ModelTier.LARGE,
            verification=VerificationLevel.DIFF if state.trigger == "mutation" else VerificationLevel.NONE,
            source="heuristic",
        )

    async def verify(
        self, state: VerificationState, candidate_answer: str
    ) -> VerificationDecision:
        del candidate_answer
        complete = not state.had_errors
        return VerificationDecision(
            complete=complete,
            evidence_sufficient=complete,
            next_action=NextAction.FINISH if complete else NextAction.INSPECT,
            source="heuristic",
        )
