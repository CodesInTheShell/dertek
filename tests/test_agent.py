from pathlib import Path

import pytest

from dertek.config import Settings
from dertek.core.agent import Agent
from dertek.core.session import Session
from dertek.hooks.manager import HookManager
from dertek.models import AgentRequest, AgentResponse, ToolCall
from dertek.router.models import RouteDecision, TaskRoute
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
