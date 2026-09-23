from __future__ import annotations

from openai import AsyncOpenAI

from dertek.models import AgentRequest, AgentResponse
from dertek.providers.openai_transport import OpenAIAPITransport, ResponsesTransport


class OpenAIProvider:
    """UI-neutral OpenAI provider backed by a selectable Responses transport."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        *,
        transport: ResponsesTransport | None = None,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("Pass either client or transport, not both")
        self.transport = transport or OpenAIAPITransport(client)
        # Retained for callers that injected an SDK client before transports existed.
        self.client = getattr(self.transport, "client", None)

    async def generate(self, request: AgentRequest) -> AgentResponse:
        return await self.transport.create(request)

    async def list_models(self) -> list[str]:
        return await self.transport.list_models()

    def validate_model(self, model: str) -> None:
        self.transport.validate_model(model)
