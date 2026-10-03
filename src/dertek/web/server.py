"""Local browser frontend for the Dertek runtime."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
from collections import deque
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, Response, abort, jsonify, render_template, request
from openai import OpenAIError
from werkzeug.exceptions import HTTPException

from dertek.config import Settings
from dertek.core.session import Session
from dertek.events import AgentEvent
from dertek.exceptions import DertekError
from dertek.models import ToolCall
from dertek.providers.openai_auth import OpenAICredentialStore
from dertek.runtime.factory import DertekRuntime, build_runtime
from dertek.runtime.storage import AppPaths, SessionStore, load_settings, update_saved_settings

APPROVAL_TIMEOUT_SECONDS = 300
MAX_RUNS_IN_MEMORY = 20
MAX_EVENTS_PER_RUN = 1000


def _event(kind: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": kind,
        "message": message,
        "data": data or {},
        "timestamp": datetime.now(UTC).isoformat(),
    }


class RunState:
    def __init__(self, run_id: str, session_id: str) -> None:
        self.id = run_id
        self.session_id = session_id
        self.condition = threading.Condition()
        self.events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS_PER_RUN)
        self.next_event_id = 1
        self.closed = False
        self.pending: dict[str, asyncio.Future[bool]] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, event: dict[str, Any]) -> None:
        with self.condition:
            item = {"schema_version": 1, "event_id": self.next_event_id, **event}
            self.next_event_id += 1
            self.events.append(item)
            self.condition.notify_all()

    def finish(self) -> None:
        with self.condition:
            self.closed = True
            self.condition.notify_all()

    async def request_approval(self, call: ToolCall, reason: str) -> bool:
        approval_id = uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        with self.condition:
            self.loop = loop
            self.pending[approval_id] = future
        self.publish(
            _event(
                "approval_request",
                f"Approve {call.name}?",
                {
                    "approval_id": approval_id,
                    "call_id": call.id,
                    "tool": call.name,
                    "arguments": call.arguments,
                    "reason": reason,
                },
            )
        )
        try:
            return await asyncio.wait_for(future, timeout=APPROVAL_TIMEOUT_SECONDS)
        except TimeoutError:
            self.publish(
                _event(
                    "approval_timeout",
                    "Approval timed out and was denied",
                    {"approval_id": approval_id},
                )
            )
            return False
        finally:
            with self.condition:
                self.pending.pop(approval_id, None)

    def answer_approval(self, approval_id: str, approved: bool) -> bool:
        with self.condition:
            future = self.pending.pop(approval_id, None)
            loop = self.loop
        if future is None or loop is None or future.done():
            return False
        loop.call_soon_threadsafe(lambda: None if future.done() else future.set_result(approved))
        self.publish(
            _event(
                "approval_resolved",
                "Approved" if approved else "Denied",
                {"approval_id": approval_id, "approved": approved},
            )
        )
        return True

    def stream(self, after: int):
        cursor = after
        while True:
            with self.condition:
                ready = [item for item in self.events if item["event_id"] > cursor]
                if not ready and not self.closed:
                    self.condition.wait(timeout=15)
                    ready = [item for item in self.events if item["event_id"] > cursor]
                closed = self.closed
            if ready:
                for item in ready:
                    cursor = item["event_id"]
                    yield f"id: {cursor}\ndata: {json.dumps(item)}\n\n"
            elif closed:
                return
            else:
                yield ": keepalive\n\n"


class WebEventSink:
    def __init__(self, controller: WebController) -> None:
        self.controller = controller

    def emit(self, event: AgentEvent) -> None:
        if event.run_id is None:
            return
        state = self.controller.runs.get(event.run_id)
        if state is not None:
            state.publish(
                {
                    "type": event.type.value,
                    "message": event.message,
                    "data": event.data,
                    "timestamp": event.timestamp.isoformat(),
                    "session_id": event.session_id,
                    "run_id": event.run_id,
                    "sequence": event.sequence,
                }
            )


class WebController:
    def __init__(
        self, paths: AppPaths | None = None, initial_workspace: Path | None = None
    ) -> None:
        self.paths = paths or AppPaths.default()
        self.store = SessionStore(self.paths)
        self.store.ensure()
        self.initial_workspace = (initial_workspace or Path.cwd()).expanduser().resolve()
        self.runtimes: dict[str, DertekRuntime] = {}
        self.runs: dict[str, RunState] = {}
        self.active_run_id: str | None = None
        self.lock = threading.Lock()
        self.sink = WebEventSink(self)

    def create_session(self, workspace: Path) -> dict[str, Any]:
        workspace = workspace.expanduser().resolve()
        if not workspace.is_dir():
            raise ValueError("Workspace must be an existing directory")
        session = Session(workspace=workspace)
        self.store.save(session)
        return session.to_dict()

    async def _approve(self, call: ToolCall, reason: str) -> bool:
        with self.lock:
            state = self.runs.get(self.active_run_id or "")
        if state is None:
            return False
        return await state.request_approval(call, reason)

    def start_run(self, session_id: str, prompt: str) -> RunState:
        if not prompt.strip():
            raise ValueError("Prompt must not be empty")
        with self.lock:
            if self.active_run_id is not None:
                raise RuntimeError("Another Dertek run is active")
            runtime = self.runtimes.get(session_id)
            context_restarted = False
            if runtime is None:
                saved = self.store.load(session_id)
                if not saved.workspace.is_dir():
                    raise ValueError("The session workspace no longer exists")
                runtime = build_runtime(
                    saved.workspace,
                    session_id=session_id,
                    events=self.sink,
                    approval_handler=self._approve,
                    paths=self.paths,
                )
                if runtime.session.auth_mode == "chatgpt" and runtime.session.history:
                    runtime.session.reset_provider_context()
                    self.store.save(runtime.session)
                    context_restarted = True
                self.runtimes[session_id] = runtime
            run_id = uuid4().hex
            state = RunState(run_id, session_id)
            self.runs[run_id] = state
            self.active_run_id = run_id
            if context_restarted:
                state.publish(
                    _event(
                        "context_restarted",
                        "ChatGPT model context restarted; saved conversation remains visible",
                    )
                )
            self._trim_runs()
        thread = threading.Thread(
            target=self._run_worker,
            args=(runtime, state, prompt.strip()),
            daemon=True,
            name=f"dertek-web-{run_id[:8]}",
        )
        thread.start()
        return state

    def _trim_runs(self) -> None:
        if len(self.runs) <= MAX_RUNS_IN_MEMORY:
            return
        completed = [key for key, state in self.runs.items() if state.closed]
        for key in completed[: len(self.runs) - MAX_RUNS_IN_MEMORY]:
            self.runs.pop(key, None)

    def _run_worker(self, runtime: DertekRuntime, state: RunState, prompt: str) -> None:
        try:
            result = asyncio.run(runtime.run(prompt, run_id=state.id))
            state.publish(_event("run_result", "Answer ready", asdict(result)))
        except Exception as exc:
            state.publish(_event("run_error", str(exc)))
        finally:
            state.finish()
            with self.lock:
                self.active_run_id = None

    def reset_context(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            if self.active_run_id is not None:
                raise RuntimeError("Wait for the active run before resetting context")
            runtime = self.runtimes.get(session_id)
            if runtime is None:
                saved = self.store.load(session_id)
                saved.reset_provider_context()
                self.store.save(saved)
                return saved.to_dict()
            runtime.session.reset_provider_context()
            transport = getattr(runtime.agent.provider, "transport", None)
            if hasattr(transport, "_history"):
                transport._history.clear()
            self.store.save(runtime.session)
            return runtime.session.to_dict()


def create_app(
    *,
    paths: AppPaths | None = None,
    initial_workspace: Path | None = None,
    port: int = 8765,
) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.json.sort_keys = False
    controller = WebController(paths, initial_workspace)
    csrf_token = secrets.token_urlsafe(32)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    @app.before_request
    def local_request_guard():
        if request.host not in allowed_hosts:
            abort(403, description="Invalid local host")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
                abort(403, description="Cross-origin request denied")
            if not secrets.compare_digest(request.headers.get("X-Dertek-CSRF", ""), csrf_token):
                abort(403, description="Missing or invalid CSRF token")

    @app.after_request
    def response_headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(exc: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=exc.description), exc.code
        return exc

    @app.errorhandler(DertekError)
    @app.errorhandler(OpenAIError)
    @app.errorhandler(ValueError)
    def domain_error(exc: Exception):
        return jsonify(error=str(exc)), 400

    def json_body() -> dict[str, Any]:

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400, description="Expected a JSON object")
        return body

    @app.get("/api/workspaces")
    def workspaces():
        path = Path(request.args.get("path") or controller.initial_workspace).expanduser().resolve()
        if not path.is_dir():
            return jsonify(error="Directory does not exist"), 404
        try:
            children = sorted(
                (
                    {"name": entry.name, "path": str(entry)}
                    for entry in path.iterdir()
                    if entry.is_dir()
                ),
                key=lambda item: item["name"].lower(),
            )
        except PermissionError:
            return jsonify(error="Cannot read this directory"), 403
        return jsonify(path=str(path), parent=str(path.parent), directories=children)

    @app.get("/api/sessions")
    def sessions():
        return jsonify(
            sessions=[
                {
                    "id": item.id,
                    "workspace": str(item.workspace),
                    "updated_at": item.updated_at,
                    "turns": item.turns,
                    "preview": item.history[-1].prompt[:100] if item.history else "",
                }
                for item in controller.store.list()
            ]
        )

    @app.post("/api/sessions")
    def create_session():
        body = json_body()
        workspace = body.get("workspace")
        if not isinstance(workspace, str) or not workspace.strip():
            return jsonify(error="Workspace path is required"), 400
        session = controller.create_session(Path(workspace))
        return jsonify(session=session), 201

    @app.get("/api/sessions/<session_id>")
    def session_detail(session_id: str):
        saved = controller.store.load(session_id)
        restarted = (
            saved.auth_mode == "chatgpt"
            and bool(saved.history)
            and session_id not in controller.runtimes
        )
        return jsonify(session=saved.to_dict(), context_will_restart=restarted)

    @app.post("/api/sessions/<session_id>/reset")
    def reset_session(session_id: str):
        try:
            return jsonify(session=controller.reset_context(session_id))
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409

    @app.post("/api/sessions/<session_id>/runs")
    def start_run(session_id: str):
        body = json_body()
        prompt = body.get("prompt")
        if not isinstance(prompt, str):
            return jsonify(error="Prompt must be text"), 400
        try:
            state = controller.start_run(session_id, prompt)
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(run_id=state.id, session_id=session_id), 202

    @app.get("/api/runs/active")
    def active_run():
        with controller.lock:
            run_id = controller.active_run_id
            state = controller.runs.get(run_id) if run_id else None
        return jsonify(
            run_id=run_id,
            session_id=state.session_id if state else None,
        )

    @app.get("/api/runs/<run_id>/events")
    def run_events(run_id: str):
        state = controller.runs.get(run_id)
        if state is None:
            return jsonify(error="Run not found"), 404
        try:
            after = max(
                0, int(request.headers.get("Last-Event-ID") or request.args.get("after") or 0)
            )
        except ValueError:
            return jsonify(error="Invalid event cursor"), 400
        return Response(
            state.stream(after),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/runs/<run_id>/approvals/<approval_id>")
    def answer_approval(run_id: str, approval_id: str):
        state = controller.runs.get(run_id)
        if state is None:
            return jsonify(error="Run not found"), 404
        body = json_body()
        approved = body.get("approved")
        if not isinstance(approved, bool):
            return jsonify(error="approved must be true or false"), 400
        if not state.answer_approval(approval_id, approved):
            return jsonify(error="Approval is no longer pending"), 409
        return jsonify(approved=approved)

    @app.get("/api/settings")
    def settings():
        with controller.paths.settings_file.open(encoding="utf-8") as handle:
            saved = json.load(handle)
        effective = load_settings(controller.paths).model_dump(mode="json")
        return jsonify(saved=saved, effective=effective)

    @app.put("/api/settings")
    def save_settings():
        body = json_body()
        values = body.get("values")
        if not isinstance(values, dict) or not values:
            return jsonify(error="values must be a non-empty object"), 400
        if set(values) - set(Settings.model_fields):
            return jsonify(error="Unknown settings field"), 400
        with controller.lock:
            if controller.active_run_id is not None:
                return jsonify(error="Wait for the active run before changing settings"), 409
            update_saved_settings(controller.paths, **values)
            controller.runtimes.clear()
        return settings()

    @app.get("/api/auth/status")
    def auth_status():
        effective = load_settings(controller.paths)
        credentials = OpenAICredentialStore(controller.paths).load()
        return jsonify(
            mode=effective.openai_auth.value,
            chatgpt_signed_in=credentials is not None,
            chatgpt_expires_soon=credentials.expires_soon() if credentials else False,
            api_key_present=bool(os.getenv("OPENAI_API_KEY")),
            jev_key_present=bool(os.getenv("TYPESAFE_API_KEY")),
        )

    @app.get("/")
    @app.get("/sessions/<session_id>")
    @app.get("/settings")
    def index(session_id: str | None = None):
        del session_id
        return render_template("index.html", csrf_token=csrf_token)

    return app
