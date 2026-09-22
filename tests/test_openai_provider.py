from types import SimpleNamespace

import pytest

from dertek.models import AgentRequest
from dertek.providers.openai import OpenAIProvider


class FakeResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(output=[], output_text="done", id="response-1")


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


@pytest.mark.asyncio
async def test_openai_provider_sends_responses_reasoning_effort() -> None:
    client = FakeClient()
    provider = OpenAIProvider(client=client)  # type: ignore[arg-type]

    await provider.generate(
        AgentRequest(
            model="gpt-5.6-luna",
            instructions="test",
            input_items="hello",
            tools=[],
            reasoning_effort="high",
        )
    )

    assert client.responses.kwargs["reasoning"] == {"effort": "high"}
