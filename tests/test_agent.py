from pathlib import Path

import pytest

from dertek.config import Settings
from dertek.core.agent import Agent
from dertek.core.session import Session
from dertek.hooks.manager import HookManager
from dertek.models import AgentRequest, AgentResponse, ToolCall
from dertek.router.models import ModelTier, RouteDecision, TaskRoute
from dertek.security.policy import CommandPolicy
from dertek.tools.registry import build_default_registry


class FakeRouter:
    async def route(self, prompt: str, workspace: Path) -> RouteDecision:
        del prompt, workspace
        return RouteDecision(TaskRoute.SEARCH, 0.99, source="test")


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: AgentRequest) -> AgentResponse:
        self.calls += 1
        if self.calls == 1:
            return AgentResponse(
                text="",
                tool_calls=[
                    ToolCall(
                        "call-1",
                        "read_file",
                        {"path": "hello.txt", "start_line": None, "end_line": None},
                    )
                ],
                continuation_token="resp-1",
            )
        assert isinstance(request.input_items, list)
        assert request.continuation_token == "resp-1"
        assert "hello world" in str(request.input_items[0]["output"])
        return AgentResponse(text="The file says hello world.", continuation_token="resp-2")


@pytest.mark.asyncio
async def test_agent_tool_loop(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello world\n", encoding="utf-8")
    settings = Settings(max_steps=4)
    provider = FakeProvider()
    agent = Agent(
        settings=settings,
        provider=provider,
        router=FakeRouter(),
        tools=build_default_registry(str(tmp_path)),
        hooks=HookManager(CommandPolicy()),
        session=Session(tmp_path),
    )
    result = await agent.run("what is in hello.txt?")
    assert result.text == "The file says hello world."
    assert result.steps == 2
    assert provider.calls == 2
    assert agent.session.history[0].prompt == "what is in hello.txt?"
    assert agent.session.history[0].response == "The file says hello world."
    assert agent.session.history[0].tools[0].output is not None


class TierRouter:
    def __init__(self, tier: ModelTier, confidence: float) -> None:
        self.tier = tier
        self.confidence = confidence

    async def route(self, prompt: str, workspace: Path) -> RouteDecision:
        del prompt, workspace
        return RouteDecision(
            TaskRoute.CHAT,
            0.99,
            source="test",
            model_tier=self.tier,
            model_confidence=self.confidence,
        )


class FinalProvider:
    request: AgentRequest | None = None

    async def generate(self, request: AgentRequest) -> AgentResponse:
        self.request = request
        return AgentResponse(text="done", continuation_token="response-1")


@pytest.mark.parametrize(
    ("tier", "confidence", "expected_model", "expected_tier", "expected_effort"),
    [
        (ModelTier.SMALL, 0.95, "small-test", "small", "high"),
        (ModelTier.SMALL, 0.40, "large-test", "large", "low"),
        (ModelTier.LARGE, 0.95, "large-test", "large", "low"),
    ],
)
@pytest.mark.asyncio
async def test_agent_selects_model_tier_with_large_as_safe_fallback(
    tmp_path: Path,
    tier: ModelTier,
    confidence: float,
    expected_model: str,
    expected_tier: str,
    expected_effort: str,
) -> None:
    provider = FinalProvider()
    agent = Agent(
        settings=Settings(small_model="small-test", large_model="large-test"),
        provider=provider,
        router=TierRouter(tier, confidence),
        tools=build_default_registry(str(tmp_path)),
        hooks=HookManager(CommandPolicy()),
        session=Session(tmp_path),
    )

    result = await agent.run("explain this")

    assert provider.request is not None
    assert provider.request.model == expected_model
    assert result.model == expected_model
    assert result.model_tier == expected_tier
    assert result.reasoning_effort == expected_effort
    assert provider.request.reasoning_effort == expected_effort
    assert agent.session.history[0].model == expected_model
    assert agent.session.history[0].reasoning_effort == expected_effort
