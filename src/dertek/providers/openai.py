from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from dertek.models import AgentRequest, AgentResponse, ToolCall


class OpenAIProvider:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI()

    async def generate(self, request: AgentRequest) -> AgentResponse:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.input_items,
            "tools": request.tools,
            "parallel_tool_calls": True,
        }
        if request.reasoning_effort:
            kwargs["reasoning"] = {"effort": request.reasoning_effort}
        if request.continuation_token:
            kwargs["previous_response_id"] = request.continuation_token

        response = await self.client.responses.create(**kwargs)

        tool_calls: list[ToolCall] = []
        for item in response.output:
            if getattr(item, "type", None) != "function_call":
                continue
            raw_arguments = getattr(item, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {"_raw_arguments": raw_arguments}
            tool_calls.append(
                ToolCall(
                    id=item.call_id,
                    name=item.name,
                    arguments=arguments,
                )
            )

        return AgentResponse(
            text=response.output_text or "",
            tool_calls=tool_calls,
            continuation_token=response.id,
        )
