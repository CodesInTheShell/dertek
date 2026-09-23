from __future__ import annotations

from typing import Protocol

from dertek.models import AgentRequest, AgentResponse


class LLMProvider(Protocol):
    async def generate(self, request: AgentRequest) -> AgentResponse: ...

    async def list_models(self) -> list[str]: ...

    def validate_model(self, model: str) -> None: ...
