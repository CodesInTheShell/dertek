from __future__ import annotations

from typing import Protocol

from dertek.models import AgentRequest, AgentResponse


class LLMProvider(Protocol):
    async def generate(self, request: AgentRequest) -> AgentResponse: ...
