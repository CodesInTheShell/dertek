from __future__ import annotations

from pathlib import Path

import pytest

from dertek.config import Settings
from dertek.core.agent import Agent
from dertek.core.session import Session
from dertek.events import AgentEvent
from dertek.hooks.manager import HookManager
from dertek.models import AgentRequest, AgentResponse, ToolCall
from dertek.router.fallback import FallbackRouter
from dertek.router.heuristic import HeuristicRouter
from dertek.router.models import (
    CheckpointDecision,
    Complexity,
    IntakeDecision,
    ModelTier,
    NextAction,
    RiskLevel,
    TaskIntent,
    TaskRoute,
    TaskScope,
    ToolProfile,
    VerificationDecision,
    VerificationLevel,
    Workflow,
)
from dertek.security.policy import CommandPolicy
from dertek.tools.registry import build_default_registry


def intake(**updates) -> IntakeDecision:
    values = {
        "route": TaskRoute.CODE,
        "confidence": 0.99,
        "source": "test-jev",
        "model_tier": ModelTier.SMALL,
        "model_confidence": 0.99,
        "intent": TaskIntent.MODIFY,
        "complexity": Complexity.BOUNDED,
        "risk": RiskLevel.LOW_MUTATION,
        "scope": TaskScope.ONE_FILE,
        "workflow": Workflow.INSPECT_FIRST,
        "tool_profile": ToolProfile.EDITING,
        "verification": VerificationLevel.NONE,
    }
    values.update(updates)
    return IntakeDecision(**values)


class ControlledEngine:
    def __init__(
        self,
        initial: IntakeDecision,
        checkpoint: CheckpointDecision | None = None,
        verification: VerificationDecision | None = None,
    ) -> None:
        self.initial = initial
        self.checkpoint_result = checkpoint or CheckpointDecision(model_tier=ModelTier.SMALL)
        self.verification_result = verification or VerificationDecision(True, True)
        self.intake_calls = 0
        self.checkpoint_calls = 0
        self.verify_calls = 0

    async def intake(self, prompt: str, workspace: Path) -> IntakeDecision:
        del prompt, workspace
        self.intake_calls += 1
        return self.initial

    async def checkpoint(self, state):
        del state
        self.checkpoint_calls += 1
        return self.checkpoint_result

    async def verify(self, state, candidate_answer: str):
        del state, candidate_answer
        self.verify_calls += 1
        return self.verification_result


class SequenceProvider:
    def __init__(self, responses: list[AgentResponse]) -> None:
        self.responses = responses
        self.requests: list[AgentRequest] = []

    async def generate(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class Collector:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def build_agent(tmp_path: Path, engine, provider, events=None, **setting_updates) -> Agent:
    return Agent(
        settings=Settings(
            small_model="luna-test",
            large_model="terra-test",
            max_steps=6,
            **setting_updates,
        ),
        provider=provider,
        router=engine,
        tools=build_default_registry(str(tmp_path)),
        hooks=HookManager(CommandPolicy()),
        session=Session(tmp_path),
        events=events,
    )


@pytest.mark.asyncio
async def test_simple_small_task_uses_one_decision_and_no_checkpoint(tmp_path: Path) -> None:
    engine = ControlledEngine(
        intake(
            route=TaskRoute.CHAT,
            intent=TaskIntent.EXPLAIN,
            risk=RiskLevel.READ_ONLY,
            workflow=Workflow.ANSWER_DIRECTLY,
            tool_profile=ToolProfile.NONE,
        )
    )
    provider = SequenceProvider([AgentResponse("answer", continuation_token="small-1")])
    agent = build_agent(tmp_path, engine, provider)

    result = await agent.run("explain this")

    assert result.model == "luna-test"
    assert result.jev_call_count == 1
    assert engine.checkpoint_calls == engine.verify_calls == 0
    assert provider.requests[0].tools == []


@pytest.mark.asyncio
async def test_plain_heuristic_fallback_reports_zero_jev_api_calls(tmp_path: Path) -> None:
    provider = SequenceProvider([AgentResponse("answer", continuation_token="large-1")])
    result = await build_agent(tmp_path, HeuristicRouter(), provider).run("explain this")
    assert result.model == "terra-test"
    assert result.jev_call_count == 0


@pytest.mark.asyncio
async def test_successful_read_only_tool_does_not_trigger_checkpoint(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n")
    engine = ControlledEngine(
        intake(
            route=TaskRoute.SEARCH,
            intent=TaskIntent.INSPECT,
            risk=RiskLevel.READ_ONLY,
            workflow=Workflow.SEARCH_FIRST,
            tool_profile=ToolProfile.READ_ONLY,
        )
    )
    provider = SequenceProvider(
        [
            AgentResponse("", [ToolCall("read-1", "read_file", {"path": "hello.txt"})], "small-1"),
            AgentResponse("found it", continuation_token="small-2"),
        ]
    )
    result = await build_agent(tmp_path, engine, provider, small_model_step_limit=3).run("find hello")
    assert result.text == "found it"
    assert engine.checkpoint_calls == 0
    assert result.jev_call_count == 1


@pytest.mark.asyncio
async def test_mutation_checkpoint_escalates_and_resets_continuation(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("old\n")
    engine = ControlledEngine(
        intake(),
        CheckpointDecision(
            next_action=NextAction.ESCALATE,
            model_tier=ModelTier.LARGE,
            verification=VerificationLevel.DIFF,
            source="test-jev",
        ),
    )
    patch = "*** Begin Patch\n*** Update File: file.txt\n@@\n-old\n+new\n*** End Patch"
    provider = SequenceProvider(
        [
            AgentResponse("", [ToolCall("patch-1", "apply_patch", {"patch": patch})], "small-1"),
            AgentResponse("updated", continuation_token="large-1"),
        ]
    )
    collector = Collector()
    agent = build_agent(tmp_path, engine, provider, events=collector)

    result = await agent.run("update file")

    assert (tmp_path / "file.txt").read_text() == "new\n"
    assert provider.requests[0].model == "luna-test"
    assert provider.requests[1].model == "terra-test"
    assert provider.requests[1].continuation_token is None
    assert isinstance(provider.requests[1].input_items, str)
    assert "Observed tool evidence" in provider.requests[1].input_items
    assert result.model_transitions[0]["from"] == "small"
    assert result.verification_status == "passed"
    assert result.jev_call_count == 3
    event_types = [event.type.value for event in collector.events]
    assert event_types.count("decision_started") == 3
    assert "model_escalated" in event_types


@pytest.mark.asyncio
async def test_failed_verification_allows_one_correction_cycle(tmp_path: Path) -> None:
    engine = ControlledEngine(
        intake(verification=VerificationLevel.REREAD),
        verification=VerificationDecision(False, False, NextAction.INSPECT, "test-jev"),
    )
    provider = SequenceProvider([AgentResponse("first", continuation_token="one"), AgentResponse("corrected", continuation_token="two")])
    result = await build_agent(tmp_path, engine, provider).run("answer carefully")
    assert engine.verify_calls == 1
    assert len(provider.requests) == 2
    assert "Verification warning" in result.text
    assert result.verification_status == "corrected_unverified"


@pytest.mark.asyncio
async def test_decision_calls_never_exceed_configured_ceiling(tmp_path: Path) -> None:
    engine = ControlledEngine(intake())
    provider = SequenceProvider(
        [
            AgentResponse("", [ToolCall("bad-1", "missing_tool", {})], "one"),
            AgentResponse("", [ToolCall("bad-2", "missing_tool", {})], "two"),
            AgentResponse("", [ToolCall("bad-3", "missing_tool", {})], "three"),
            AgentResponse("best answer", continuation_token="four"),
        ]
    )
    result = await build_agent(tmp_path, engine, provider, max_jev_calls_per_turn=4).run("try")
    assert engine.checkpoint_calls == 2
    assert engine.verify_calls == 1
    assert result.jev_call_count == 4


class BrokenEngine:
    async def intake(self, prompt, workspace):
        raise RuntimeError("intake down")

    async def checkpoint(self, state):
        raise RuntimeError("checkpoint down")

    async def verify(self, state, candidate_answer):
        raise RuntimeError("verify down")


@pytest.mark.asyncio
async def test_fallback_handles_each_decision_phase(tmp_path: Path) -> None:
    fallback = FallbackRouter(BrokenEngine(), HeuristicRouter())
    initial = await fallback.intake("change this file", tmp_path)
    assert initial.source == "heuristic-after-jev-error"
    from dertek.router.models import CheckpointState, VerificationState

    checkpoint = await fallback.checkpoint(CheckpointState("x", 1, "tool_error", initial, ModelTier.LARGE, [{"is_error": True}]))
    assert checkpoint.source == "heuristic-after-jev-error"
    verification = await fallback.verify(VerificationState("x", initial, ModelTier.LARGE, had_errors=True), "answer")
    assert verification.source == "heuristic-after-jev-error"
    assert not verification.complete
