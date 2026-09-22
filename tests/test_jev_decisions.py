from pathlib import Path

from dertek.router.jev import TypeSafeJevRouter
from dertek.router.models import (
    Complexity,
    ModelTier,
    RiskLevel,
    TaskIntent,
    TaskRoute,
    TaskScope,
    ToolProfile,
    VerificationLevel,
    Workflow,
)


class Answer:
    def __init__(self, choice: str, confidence: float = 0.95) -> None:
        self.choice = choice
        self.confidence = confidence
        self.probabilities = {choice: confidence}


def test_jev_intake_maps_all_typed_answers(monkeypatch) -> None:
    answers = {
        "route": Answer("code"),
        "intent": Answer("modify"),
        "complexity": Answer("bounded"),
        "risk": Answer("low_mutation"),
        "scope": Answer("one_file"),
        "workflow": Answer("inspect_first"),
        "tool_profile": Answer("editing"),
        "model_tier": Answer("small", 0.91),
        "verification": Answer("targeted_test"),
    }
    monkeypatch.setattr(TypeSafeJevRouter, "_call", staticmethod(lambda state, questions: answers))

    decision = TypeSafeJevRouter._intake_sync("change it", Path("/tmp/work"))

    assert decision.route == TaskRoute.CODE
    assert decision.intent == TaskIntent.MODIFY
    assert decision.complexity == Complexity.BOUNDED
    assert decision.risk == RiskLevel.LOW_MUTATION
    assert decision.scope == TaskScope.ONE_FILE
    assert decision.workflow == Workflow.INSPECT_FIRST
    assert decision.tool_profile == ToolProfile.EDITING
    assert decision.model_tier == ModelTier.SMALL
    assert decision.verification == VerificationLevel.TARGETED_TEST
    assert set(decision.judgments) == set(answers)
