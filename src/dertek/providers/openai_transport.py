from __future__ import annotations

import json
from typing import Any, Protocol

import httpx
from openai import AsyncOpenAI

from dertek.exceptions import AuthenticationError, ConfigurationError
from dertek.models import AgentRequest, AgentResponse, ToolCall
from dertek.providers.openai_auth import OpenAIAuthManager

CHATGPT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CHATGPT_MODELS = frozenset(
    {
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-5.6",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
    }
)


class ResponsesTransport(Protocol):
    async def create(self, request: AgentRequest) -> AgentResponse: ...

    async def list_models(self) -> list[str]: ...

    def validate_model(self, model: str) -> None: ...


def _request_payload(request: AgentRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "instructions": request.instructions,
        "input": request.input_items,
        "tools": request.tools,
        "parallel_tool_calls": True,
    }
    if request.reasoning_effort:
        payload["reasoning"] = {"effort": request.reasoning_effort}
    if request.continuation_token:
        payload["previous_response_id"] = request.continuation_token
    return payload


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raw = value if isinstance(value, str) else "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw_arguments": raw}
    return parsed if isinstance(parsed, dict) else {"_raw_arguments": raw}


def _response_from_mapping(value: dict[str, Any], fallback_text: str = "") -> AgentResponse:
    output = value.get("output")
    tool_calls: list[ToolCall] = []
    text_parts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=str(item.get("call_id") or item.get("id") or ""),
                        name=str(item.get("name") or ""),
                        arguments=_arguments(item.get("arguments")),
                    )
                )
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") in {
                        "output_text",
                        "text",
                    }:
                        text_parts.append(str(content.get("text") or ""))
    text = "".join(text_parts) or str(value.get("output_text") or fallback_text)
    return AgentResponse(
        text=text,
        tool_calls=tool_calls,
        continuation_token=str(value["id"]) if value.get("id") else None,
    )


class OpenAIAPITransport:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI()

    async def create(self, request: AgentRequest) -> AgentResponse:
        response = await self.client.responses.create(**_request_payload(request))
        output = []
        for item in response.output:
            if hasattr(item, "model_dump"):
                output.append(item.model_dump())
            else:
                output.append(
                    {
                        "type": getattr(item, "type", None),
                        "call_id": getattr(item, "call_id", None),
                        "name": getattr(item, "name", None),
                        "arguments": getattr(item, "arguments", None),
                    }
                )
        return _response_from_mapping(
            {
                "id": response.id,
                "output": output,
                "output_text": response.output_text or "",
            }
        )

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return sorted(model.id for model in page.data)

    def validate_model(self, model: str) -> None:
        if not model.strip():
            raise ConfigurationError("OpenAI model names may not be empty")


class ChatGPTCodexTransport:
    def __init__(
        self,
        auth: OpenAIAuthManager,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str = CHATGPT_CODEX_BASE_URL,
    ) -> None:
        self.auth = auth
        self.client = client
        self.base_url = base_url.rstrip("/")
        self._history: list[dict[str, Any]] = []

    def validate_model(self, model: str) -> None:
        if model not in CHATGPT_MODELS:
            supported = ", ".join(sorted(CHATGPT_MODELS))
            raise ConfigurationError(
                f"Model '{model}' is not available through Dertek's ChatGPT transport. "
                f"Supported models: {supported}"
            )

    def _payload(
        self, request: AgentRequest
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        payload = _request_payload(request)
        if isinstance(request.input_items, str):
            current_input: list[dict[str, Any]] = [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": request.input_items}
                    ],
                }
            ]
        else:
            current_input = list(request.input_items)
        if request.continuation_token is None:
            self._history.clear()
        payload.pop("previous_response_id", None)
        payload["input"] = [*self._history, *current_input]
        payload.update(
            {
                "tool_choice": "auto",
                "include": ["reasoning.encrypted_content"],
                "stream": True,
                "store": False,
            }
        )
        return payload, current_input

    async def list_models(self) -> list[str]:
        return sorted(CHATGPT_MODELS)

    async def _send(
        self, payload: dict[str, Any], *, force_refresh: bool = False
    ) -> httpx.Response:
        credentials = await self.auth.credentials(force_refresh=force_refresh)
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "chatgpt-account-id": credentials.account_id,
            "originator": "codex_cli_rs",
            "OpenAI-Beta": "responses=experimental",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "dertek-cli/0.1",
        }
        request = httpx.Request(
            "POST", f"{self.base_url}/responses", headers=headers, json=payload
        )
        if self.client is not None:
            return await self.client.send(request, stream=True)
        client = httpx.AsyncClient(timeout=None)
        response = await client.send(request, stream=True)
        response.extensions["dertek_client"] = client
        return response

    @staticmethod
    async def _close(response: httpx.Response) -> None:
        await response.aclose()
        client = response.extensions.get("dertek_client")
        if isinstance(client, httpx.AsyncClient):
            await client.aclose()

    async def create(self, request: AgentRequest) -> AgentResponse:
        self.validate_model(request.model)
        payload, current_input = self._payload(request)
        response = await self._send(payload)
        if response.status_code == 401:
            await self._close(response)
            response = await self._send(payload, force_refresh=True)
        if response.status_code == 401:
            await self._close(response)
            raise AuthenticationError(
                "ChatGPT rejected the refreshed credentials; run 'dertek auth login' again"
            )
        if not response.is_success:
            status = response.status_code
            body = await response.aread()
            detail = ""
            try:
                error = json.loads(body).get("error", {})
                if isinstance(error, dict):
                    message = str(error.get("message") or "").strip()
                    code = str(error.get("code") or "").strip()
                    param = str(error.get("param") or "").strip()
                    parts = [message[:500]] if message else []
                    if code:
                        parts.append(f"code={code[:100]}")
                    if param:
                        parts.append(f"param={param[:100]}")
                    detail = f": {'; '.join(parts)}" if parts else ""
            except (json.JSONDecodeError, AttributeError):
                pass
            await self._close(response)
            raise AuthenticationError(f"ChatGPT model request failed ({status}){detail}")

        completed: dict[str, Any] | None = None
        output_items: list[dict[str, Any]] = []
        text_parts: list[str] = []
        try:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise AuthenticationError("ChatGPT returned a malformed event stream") from exc
                if not isinstance(event, dict):
                    continue
                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    text_parts.append(str(event.get("delta") or ""))
                if event_type == "response.output_item.done" and isinstance(
                    event.get("item"), dict
                ):
                    output_items.append(event["item"])
                if event_type == "response.completed" and isinstance(
                    event.get("response"), dict
                ):
                    completed = dict(event["response"])
                if event_type == "response.incomplete":
                    response_value = event.get("response")
                    details = (
                        response_value.get("incomplete_details", {})
                        if isinstance(response_value, dict)
                        else {}
                    )
                    reason = details.get("reason", "unknown") if isinstance(details, dict) else "unknown"
                    raise AuthenticationError(
                        f"ChatGPT returned an incomplete response: {reason}"
                    )
                if event_type in {"error", "response.failed"}:
                    response_value = event.get("response")
                    error = (
                        response_value.get("error", {})
                        if isinstance(response_value, dict)
                        else event.get("error", {})
                    )
                    message = error.get("message") if isinstance(error, dict) else None
                    code = error.get("code") if isinstance(error, dict) else None
                    detail = str(message or code or "unknown error")[:500]
                    raise AuthenticationError(
                        f"ChatGPT reported a model request failure: {detail}"
                    )
        finally:
            await self._close(response)
        if completed is None:
            raise AuthenticationError("ChatGPT response stream ended before completion")
        output = completed.get("output")
        if not isinstance(output, list) or not output:
            completed["output"] = output_items
            output = output_items
        if isinstance(output, list):
            self._history.extend(current_input)
            self._history.extend(item for item in output if isinstance(item, dict))
        return _response_from_mapping(completed, "".join(text_parts))
