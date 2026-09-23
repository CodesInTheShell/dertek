from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from dertek.events import AgentEvent, EventSink, EventType, NullEventSink
from dertek.exceptions import AuthenticationError, ConfigurationError
from dertek.runtime.storage import AppPaths, write_json_atomic

OAUTH_ISSUER = "https://auth.openai.com"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_SCOPES = (
    "openid profile email offline_access "
    "api.connectors.read api.connectors.invoke"
)
OAUTH_CALLBACK_PATH = "/auth/callback"
OAUTH_CALLBACK_PORTS = (1455, 1457)
OAUTH_TIMEOUT_SECONDS = 300
DEVICE_TIMEOUT_SECONDS = 900


@dataclass(slots=True)
class OpenAICredentials:
    access_token: str
    refresh_token: str
    expires_at: float
    account_id: str
    token_type: str = "Bearer"
    scope: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OpenAICredentials:
        try:
            return cls(
                access_token=str(value["access_token"]),
                refresh_token=str(value["refresh_token"]),
                expires_at=float(value["expires_at"]),
                account_id=str(value["account_id"]),
                token_type=str(value.get("token_type", "Bearer")),
                scope=str(value["scope"]) if value.get("scope") else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("OpenAI credential file is invalid") from exc

    def expires_soon(self, leeway_seconds: int = 60) -> bool:
        return self.expires_at <= time.time() + leeway_seconds


class OpenAICredentialStore:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or AppPaths.default()

    @property
    def path(self) -> Path:
        return self.paths.openai_auth_file

    def save(self, credentials: OpenAICredentials) -> None:
        self.paths.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.paths.root.chmod(0o700)
        write_json_atomic(self.path, asdict(credentials))

    def load(self) -> OpenAICredentials | None:
        try:
            with self.path.open(encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise ConfigurationError("OpenAI credential file is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ConfigurationError("OpenAI credential file is invalid")
        self.path.chmod(0o600)
        return OpenAICredentials.from_dict(value)

    def delete(self) -> bool:
        if not self.path.exists():
            return False
        self.path.unlink()
        return True


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _authorize_url(redirect_uri: str, challenge: str, state: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": OAUTH_SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "dertek",
        }
    )
    return f"{OAUTH_ISSUER}/oauth/authorize?{query}"


def _callback_server(
    handler: type[BaseHTTPRequestHandler],
) -> ThreadingHTTPServer:
    for port in OAUTH_CALLBACK_PORTS:
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError:
            continue
    ports = " or ".join(str(port) for port in OAUTH_CALLBACK_PORTS)
    raise AuthenticationError(
        f"Cannot start the ChatGPT login callback on localhost port {ports}. "
        "Close the program using those ports, or run "
        "'dertek auth login --device-code'."
    )


def _jwt_claims(token: str) -> dict[str, Any]:
    """Read OAuth claims used only for routing metadata, never authorization."""
    try:
        segment = token.split(".")[1]
        padding = "=" * (-len(segment) % 4)
        value = json.loads(base64.urlsafe_b64decode(segment + padding))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("OpenAI returned an unreadable identity token") from exc
    if not isinstance(value, dict):
        raise AuthenticationError("OpenAI returned an invalid identity token")
    return value


def _account_id(tokens: dict[str, Any]) -> str:
    for name in ("id_token", "access_token"):
        token = tokens.get(name)
        if not isinstance(token, str):
            continue
        claims = _jwt_claims(token)
        auth = claims.get("https://api.openai.com/auth")
        if isinstance(auth, dict) and auth.get("chatgpt_account_id"):
            return str(auth["chatgpt_account_id"])
    raise AuthenticationError("The ChatGPT account ID was missing from the OAuth response")


class OpenAIAuthManager:
    def __init__(
        self,
        store: OpenAICredentialStore | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        events: EventSink | None = None,
    ) -> None:
        self.store = store or OpenAICredentialStore()
        self.client = client
        self.events = events or NullEventSink()

    def _emit(self, event_type: EventType, message: str, **data: Any) -> None:
        self.events.emit(AgentEvent(event_type, message, data))

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        if self.client is not None:
            return await self.client.post(url, **kwargs)
        async with httpx.AsyncClient(timeout=30) as client:
            return await client.post(url, **kwargs)

    def _credentials_from_tokens(
        self, tokens: dict[str, Any], previous: OpenAICredentials | None = None
    ) -> OpenAICredentials:
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token") or (
            previous.refresh_token if previous else None
        )
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise AuthenticationError("OpenAI OAuth did not return the required credentials")
        expires_in = float(tokens.get("expires_in", 3600))
        return OpenAICredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
            account_id=_account_id(tokens) if previous is None else previous.account_id,
            token_type=str(tokens.get("token_type", "Bearer")),
            scope=str(tokens["scope"]) if tokens.get("scope") else None,
        )

    async def _exchange(
        self, code: str, redirect_uri: str, verifier: str
    ) -> OpenAICredentials:
        response = await self._post(
            f"{OAUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": OAUTH_CLIENT_ID,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise AuthenticationError(f"OpenAI token exchange failed ({response.status_code})")
        return self._credentials_from_tokens(response.json())

    async def login_browser(
        self,
        *,
        open_browser: bool = True,
        show_url: Callable[[str], None] | None = None,
    ) -> OpenAICredentials:
        self._emit(EventType.AUTH_STARTED, "ChatGPT browser login started", method="browser")
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(32)
        result: dict[str, str] = {}
        callback_received = threading.Event()

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                query = parse_qs(urlparse(self.path).query)
                if self.path.split("?", 1)[0] != OAUTH_CALLBACK_PATH:
                    self.send_error(404)
                    return
                for key in ("code", "state", "error"):
                    if query.get(key):
                        result[key] = query[key][0]
                callback_received.set()
                ok = "code" in result and result.get("state") == state
                body = (
                    b"ChatGPT login complete. You may close this window."
                    if ok
                    else b"ChatGPT login failed. Return to Dertek for details."
                )
                self.send_response(200 if ok else 400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

        server = _callback_server(CallbackHandler)
        redirect_uri = f"http://localhost:{server.server_port}{OAUTH_CALLBACK_PATH}"
        url = _authorize_url(redirect_uri, challenge, state)
        if show_url:
            show_url(url)
        if open_browser:
            webbrowser.open(url)
        server_task = asyncio.create_task(
            asyncio.to_thread(server.serve_forever, poll_interval=0.1)
        )
        try:
            await asyncio.wait_for(
                asyncio.to_thread(callback_received.wait), timeout=OAUTH_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            self._emit(EventType.AUTH_FAILED, "ChatGPT browser login timed out", method="browser")
            raise AuthenticationError(
                "ChatGPT browser login timed out after 5 minutes"
            ) from exc
        finally:
            await asyncio.to_thread(server.shutdown)
            await server_task
            server.server_close()

        if result.get("state") != state:
            raise AuthenticationError("ChatGPT login callback state did not match")
        if result.get("error"):
            raise AuthenticationError(f"ChatGPT login was rejected: {result['error']}")
        if not result.get("code"):
            raise AuthenticationError("ChatGPT login callback did not contain a code")
        credentials = await self._exchange(result["code"], redirect_uri, verifier)
        self.store.save(credentials)
        self._emit(EventType.AUTH_FINISHED, "ChatGPT login completed", method="browser")
        return credentials

    async def login_device(
        self, show_code: Callable[[str, str], None] | None = None
    ) -> OpenAICredentials:
        self._emit(EventType.AUTH_STARTED, "ChatGPT device login started", method="device-code")
        response = await self._post(
            f"{OAUTH_ISSUER}/api/accounts/deviceauth/usercode",
            json={"client_id": OAUTH_CLIENT_ID},
        )
        if not response.is_success:
            raise AuthenticationError(f"Device login could not start ({response.status_code})")
        value = response.json()
        try:
            device_auth_id = str(value["device_auth_id"])
            user_code = str(value.get("user_code") or value["usercode"])
            interval = max(int(value.get("interval", 5)), 1)
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("OpenAI returned an invalid device-code response") from exc
        verification_url = f"{OAUTH_ISSUER}/codex/device"
        if show_code:
            show_code(verification_url, user_code)
        deadline = time.monotonic() + DEVICE_TIMEOUT_SECONDS
        authorization: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            poll = await self._post(
                f"{OAUTH_ISSUER}/api/accounts/deviceauth/token",
                json={"device_auth_id": device_auth_id, "user_code": user_code},
            )
            if poll.is_success:
                authorization = poll.json()
                break
            if poll.status_code not in (403, 404):
                raise AuthenticationError(f"Device login failed ({poll.status_code})")
            await asyncio.sleep(interval)
        if authorization is None:
            raise AuthenticationError("ChatGPT device login timed out")
        credentials = await self._exchange(
            str(authorization["authorization_code"]),
            f"{OAUTH_ISSUER}/deviceauth/callback",
            str(authorization["code_verifier"]),
        )
        self.store.save(credentials)
        self._emit(EventType.AUTH_FINISHED, "ChatGPT login completed", method="device-code")
        return credentials

    async def refresh(self, credentials: OpenAICredentials) -> OpenAICredentials:
        response = await self._post(
            f"{OAUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": OAUTH_CLIENT_ID,
                "refresh_token": credentials.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise AuthenticationError(
                f"ChatGPT credentials could not be refreshed ({response.status_code}); "
                "run 'dertek auth login' again"
            )
        refreshed = self._credentials_from_tokens(response.json(), credentials)
        self.store.save(refreshed)
        return refreshed

    async def credentials(self, *, force_refresh: bool = False) -> OpenAICredentials:
        credentials = self.store.load()
        if credentials is None:
            raise AuthenticationError(
                "ChatGPT is not signed in; run 'dertek auth login' first"
            )
        if force_refresh or credentials.expires_soon():
            credentials = await self.refresh(credentials)
        return credentials

    def logout(self) -> bool:
        removed = self.store.delete()
        self._emit(EventType.AUTH_LOGGED_OUT, "ChatGPT credentials removed")
        return removed
