import base64
import json
import stat
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from dertek.config import OpenAIAuthMode
from dertek.exceptions import AuthenticationError
from dertek.models import AgentRequest
from dertek.providers.openai_auth import (
    OAUTH_CALLBACK_PORTS,
    OAUTH_CLIENT_ID,
    OAUTH_SCOPES,
    OpenAIAuthManager,
    OpenAICredentials,
    OpenAICredentialStore,
    _authorize_url,
    _pkce_pair,
)
from dertek.providers.openai_transport import ChatGPTCodexTransport
from dertek.runtime.storage import AppPaths, SessionStore, load_settings


def _token(account_id: str = "account-123") -> str:
    header = base64.urlsafe_b64encode(b"{}").rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}
        ).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


def _credentials(*, expired: bool = False) -> OpenAICredentials:
    return OpenAICredentials(
        access_token=_token(),
        refresh_token="refresh-secret",
        expires_at=time.time() - 1 if expired else time.time() + 3600,
        account_id="account-123",
    )


def test_pkce_is_unique_and_uses_sha256_challenge() -> None:
    first = _pkce_pair()
    second = _pkce_pair()
    assert first[0] != second[0]
    assert first[0] != first[1]
    assert "=" not in first[1]


def test_authorize_url_uses_registered_localhost_callback() -> None:
    redirect_uri = f"http://localhost:{OAUTH_CALLBACK_PORTS[0]}/auth/callback"
    url = urlparse(_authorize_url(redirect_uri, "challenge", "state"))
    query = parse_qs(url.query)

    assert query["client_id"] == [OAUTH_CLIENT_ID]
    assert query["redirect_uri"] == [redirect_uri]
    assert query["scope"] == [OAUTH_SCOPES]
    assert query["code_challenge_method"] == ["S256"]
    assert query["originator"] == ["dertek"]


def test_credentials_are_owner_only_and_not_in_settings(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    SessionStore(paths).ensure()
    store = OpenAICredentialStore(paths)
    store.save(_credentials())

    assert stat.S_IMODE(paths.auth_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(paths.openai_auth_file.stat().st_mode) == 0o600
    assert "refresh-secret" not in paths.settings_file.read_text(encoding="utf-8")


def test_openai_auth_setting_defaults_and_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    SessionStore(paths).ensure()
    assert load_settings(paths).openai_auth == OpenAIAuthMode.API_KEY
    monkeypatch.setenv("DERTEK_OPENAI_AUTH", "chatgpt")
    assert load_settings(paths).openai_auth == OpenAIAuthMode.CHATGPT


@pytest.mark.asyncio
async def test_refresh_rotates_credentials_atomically(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    store = OpenAICredentialStore(paths)
    store.save(_credentials(expired=True))

    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert request.url.path == "/oauth/token"
        assert f"client_id={OAUTH_CLIENT_ID}" in body
        return httpx.Response(
            200,
            json={
                "access_token": _token(),
                "refresh_token": "rotated-secret",
                "expires_in": 3600,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    manager = OpenAIAuthManager(store, client=client)
    refreshed = await manager.credentials()
    await client.aclose()

    assert refreshed.refresh_token == "rotated-secret"
    assert store.load().refresh_token == "rotated-secret"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_chatgpt_transport_uses_codex_endpoint_and_headers(tmp_path: Path) -> None:
    store = OpenAICredentialStore(AppPaths(tmp_path / ".dertek"))
    store.save(_credentials())
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        event = {
            "type": "response.completed",
            "response": {
                "id": "response-1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "read_file",
                        "arguments": '{"path":"README.md"}',
                    }
                ],
                "output_text": "done",
            },
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = ChatGPTCodexTransport(
        OpenAIAuthManager(store), client=client
    )
    response = await transport.create(
        AgentRequest(
            model="gpt-5.6-luna",
            instructions="Work carefully",
            input_items="Read the README",
            tools=[],
            reasoning_effort="high",
        )
    )
    await client.aclose()

    request = seen[0]
    payload = json.loads(request.content)
    assert str(request.url) == "https://chatgpt.com/backend-api/codex/responses"
    assert request.headers["authorization"].startswith("Bearer ")
    assert request.headers["chatgpt-account-id"] == "account-123"
    assert payload["stream"] is True
    assert payload["store"] is False
    assert payload["tool_choice"] == "auto"
    assert payload["include"] == ["reasoning.encrypted_content"]
    assert payload["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Read the README"}],
        }
    ]
    assert "temperature" not in payload
    assert "max_output_tokens" not in payload
    assert response.tool_calls[0].name == "read_file"


@pytest.mark.asyncio
async def test_chatgpt_transport_refreshes_once_on_401(tmp_path: Path) -> None:
    store = OpenAICredentialStore(AppPaths(tmp_path / ".dertek"))
    store.save(_credentials())
    model_calls = 0

    async def model_handler(request: httpx.Request) -> httpx.Response:
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            return httpx.Response(401)
        event = {
            "type": "response.completed",
            "response": {"id": "response-2", "output": [], "output_text": "ok"},
        }
        return httpx.Response(200, content=f"data: {json.dumps(event)}\n\n")

    class RefreshingAuth:
        calls = 0

        async def credentials(self, *, force_refresh: bool = False) -> OpenAICredentials:
            self.calls += 1
            return _credentials()

    client = httpx.AsyncClient(transport=httpx.MockTransport(model_handler))
    auth = RefreshingAuth()
    transport = ChatGPTCodexTransport(auth, client=client)  # type: ignore[arg-type]
    await transport.create(
        AgentRequest("gpt-5.6-luna", "test", "hello", [])
    )
    await client.aclose()

    assert model_calls == 2
    assert auth.calls == 2


@pytest.mark.asyncio
async def test_chatgpt_transport_reads_output_item_done(tmp_path: Path) -> None:
    store = OpenAICredentialStore(AppPaths(tmp_path / ".dertek"))
    store.save(_credentials())

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        output_event = {
            "type": "response.output_item.done",
            "item": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "This is the repo."}],
            },
        }
        completed_event = {
            "type": "response.completed",
            "response": {"id": "response-terra"},
        }
        content = (
            f"data: {json.dumps(output_event)}\n\n"
            f"data: {json.dumps(completed_event)}\n\n"
        )
        return httpx.Response(200, content=content)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = ChatGPTCodexTransport(OpenAIAuthManager(store), client=client)
    response = await transport.create(
        AgentRequest("gpt-5.6-terra", "test", "What is this repo?", [])
    )
    await client.aclose()

    assert response.text == "This is the repo."
    assert response.continuation_token == "response-terra"


def test_chatgpt_transport_replays_local_history_without_previous_response_id(
    tmp_path: Path,
) -> None:
    store = OpenAICredentialStore(AppPaths(tmp_path / ".dertek"))
    transport = ChatGPTCodexTransport(OpenAIAuthManager(store))
    transport._history.append(
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hello"}],
        }
    )

    payload, current = transport._payload(
        AgentRequest(
            "gpt-5.6-terra",
            "test",
            "What is this repo?",
            [],
            continuation_token="response-not-stored",
        )
    )

    assert "previous_response_id" not in payload
    assert payload["input"][0]["role"] == "assistant"
    assert payload["input"][1] == current[0]

    reset_payload, _ = transport._payload(
        AgentRequest("gpt-5.6-terra", "test", "Start over", [])
    )
    assert len(reset_payload["input"]) == 1


@pytest.mark.asyncio
async def test_chatgpt_transport_rejects_unsupported_model(tmp_path: Path) -> None:
    store = OpenAICredentialStore(AppPaths(tmp_path / ".dertek"))
    store.save(_credentials())
    transport = ChatGPTCodexTransport(OpenAIAuthManager(store))
    with pytest.raises(Exception, match="not available"):
        await transport.create(AgentRequest("unknown-model", "test", "hello", []))


def test_missing_credentials_has_actionable_error(tmp_path: Path) -> None:
    manager = OpenAIAuthManager(OpenAICredentialStore(AppPaths(tmp_path / ".dertek")))
    with pytest.raises(AuthenticationError, match="dertek auth login"):
        import asyncio

        asyncio.run(manager.credentials())
