from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from typesafe_sdk import Choice, TypeSafeClient

from dertek.router.models import (
    CheckpointDecision,
    CheckpointState,
    Complexity,
    FailureCategory,
    IntakeDecision,
    Judgment,
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


def _criteria(enum_type: type, descriptions: dict[str, str]) -> dict[str, str]:
    return {item.value: descriptions.get(item.value, item.value.replace("_", " ")) for item in enum_type}


class TypeSafeJevRouter:
    async def route(self, prompt: str, workspace: Path) -> IntakeDecision:
        return await self.intake(prompt, workspace)

    async def intake(self, prompt: str, workspace: Path) -> IntakeDecision:
        return await asyncio.to_thread(self._intake_sync, prompt, workspace)

    async def checkpoint(self, state: CheckpointState) -> CheckpointDecision:
        return await asyncio.to_thread(self._checkpoint_sync, state)

    async def verify(
        self, state: VerificationState, candidate_answer: str
    ) -> VerificationDecision:
        return await asyncio.to_thread(self._verify_sync, state, candidate_answer)

    @staticmethod
    def _call(state: dict[str, Any], questions: dict[str, Choice]) -> dict[str, Any]:
        with TypeSafeClient() as client:
            response = client.system_one(state=state, questions=questions)
        answers: Any = getattr(response, "answers", None) or getattr(response, "choices", None)
        if answers is None:
            raise RuntimeError("TypeSafe response did not contain answers/choices")
        return dict(answers)

    @classmethod
    def _intake_sync(cls, prompt: str, workspace: Path) -> IntakeDecision:
        answers = cls._call(
            {"prompt": prompt, "workspace_name": workspace.name, "application": "Dertek coding agent"},
            {
                "route": Choice(instructions="Primary task type?", criteria=_criteria(TaskRoute, {})),
                "intent": Choice(instructions="What action does the user primarily request?", criteria=_criteria(TaskIntent, {})),
                "complexity": Choice(instructions="How much reasoning is required?", criteria=_criteria(Complexity, {
                    "trivial": "Direct, narrow, and obvious.", "bounded": "Limited and well-defined.",
                    "complex": "Ambiguous, architectural, debugging-heavy, or multi-step.",
                })),
                "risk": Choice(instructions="What is the semantic change risk?", criteria=_criteria(RiskLevel, {})),
                "scope": Choice(instructions="What repository scope is expected?", criteria=_criteria(TaskScope, {})),
                "workflow": Choice(instructions="Which workflow should the agent begin with?", criteria=_criteria(Workflow, {})),
                "tool_profile": Choice(instructions="Which bounded tool group is needed?", criteria=_criteria(ToolProfile, {})),
                "model_tier": Choice(
                    instructions="Which generative LLM tier should perform the task?",
                    criteria={"small": "Narrow bounded generative work.", "large": "Complex, risky, ambiguous, or broad work."},
                ),
                "verification": Choice(instructions="What verification should the workflow seek?", criteria=_criteria(VerificationLevel, {})),
            },
        )
        judgments = {name: cls._judgment(answer) for name, answer in answers.items()}
        route = judgments["route"]
        model = judgments["model_tier"]
        return IntakeDecision(
            route=TaskRoute(route.choice),
            confidence=route.confidence,
            probabilities=route.probabilities,
            source="typesafe-jev",
            model_tier=ModelTier(model.choice),
            model_confidence=model.confidence,
            model_probabilities=model.probabilities,
            intent=TaskIntent(judgments["intent"].choice),
            complexity=Complexity(judgments["complexity"].choice),
            risk=RiskLevel(judgments["risk"].choice),
            scope=TaskScope(judgments["scope"].choice),
            workflow=Workflow(judgments["workflow"].choice),
            tool_profile=ToolProfile(judgments["tool_profile"].choice),
            verification=VerificationLevel(judgments["verification"].choice),
            judgments=judgments,
        )

    @classmethod
    def _checkpoint_sync(cls, state: CheckpointState) -> CheckpointDecision:
        answers = cls._call(
            {"checkpoint": asdict(state)},
            {
                "progress": Choice(instructions="What is the current progress state?", criteria=_criteria(ProgressState, {})),
                "failure": Choice(instructions="Classify the most important failure.", criteria=_criteria(FailureCategory, {})),
                "scope_expanded": Choice(instructions="Did discovered scope exceed the intake estimate?", criteria={"yes": "Scope expanded.", "no": "Scope did not expand."}),
                "next_action": Choice(instructions="What should the agent do next?", criteria=_criteria(NextAction, {})),
                "model_tier": Choice(instructions="Which LLM tier should continue?", criteria={"small": "Bounded work remains.", "large": "Escalation is warranted."}),
                "verification": Choice(instructions="What verification is now appropriate?", criteria=_criteria(VerificationLevel, {})),
            },
        )
        judgments = {name: cls._judgment(answer) for name, answer in answers.items()}
        return CheckpointDecision(
            progress=ProgressState(judgments["progress"].choice),
            failure=FailureCategory(judgments["failure"].choice),
            scope_expanded=judgments["scope_expanded"].choice == "yes",
            next_action=NextAction(judgments["next_action"].choice),
            model_tier=ModelTier(judgments["model_tier"].choice),
            verification=VerificationLevel(judgments["verification"].choice),
            source="typesafe-jev",
            judgments=judgments,
        )

    @classmethod
    def _verify_sync(
        cls, state: VerificationState, candidate_answer: str
    ) -> VerificationDecision:
        answers = cls._call(
            {"verification": asdict(state), "candidate_answer": candidate_answer},
            {
                "complete": Choice(instructions="Does the answer satisfy the explicit user request?", criteria={"yes": "Complete.", "no": "Incomplete."}),
                "evidence": Choice(instructions="Is the answer supported by sufficient observed evidence?", criteria={"sufficient": "Evidence is sufficient.", "insufficient": "More evidence is needed."}),
                "next_action": Choice(instructions="What should happen next?", criteria=_criteria(NextAction, {})),
            },
        )
        judgments = {name: cls._judgment(answer) for name, answer in answers.items()}
        return VerificationDecision(
            complete=judgments["complete"].choice == "yes",
            evidence_sufficient=judgments["evidence"].choice == "sufficient",
            next_action=NextAction(judgments["next_action"].choice),
            source="typesafe-jev",
            judgments=judgments,
        )

    @staticmethod
    def _judgment(answer: Any) -> Judgment:
        choice = str(answer.choice)
        probabilities = {str(key): float(value) for key, value in dict(getattr(answer, "probabilities", {}) or {}).items()}
        confidence = getattr(answer, "confidence", None)
        if confidence is None:
            confidence = probabilities.get(choice, 0.0)
        return Judgment(choice, float(confidence), probabilities)
