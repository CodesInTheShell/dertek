from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from dertek.config import ApprovalMode, OpenAIAuthMode
from dertek.core.agent import Agent, ApprovalHandler, deny_approval
from dertek.core.session import Session
from dertek.events import AgentEvent, EventSink, EventType, NullEventSink
from dertek.hooks.manager import HookManager
from dertek.models import AgentRunResult
from dertek.providers.factory import build_provider
from dertek.router.factory import build_router
from dertek.runtime.storage import AppPaths, SessionStore, load_settings
from dertek.security.policy import CommandPolicy
from dertek.tools.registry import build_default_registry


class ContextualEventSink:
    """Adds stable run metadata while forwarding events to a UI callback."""

    def __init__(self, delegate: EventSink | None = None) -> None:
        self.delegate = delegate or NullEventSink()
        self.session_id: str | None = None
        self.run_id: str | None = None
        self.sequence = 0

    def begin(self, session_id: str) -> str:
        self.session_id = session_id
        self.run_id = uuid4().hex
        self.sequence = 0
        return self.run_id

    def emit(self, event: AgentEvent) -> None:
        self.sequence += 1
        self.delegate.emit(
            replace(
                event,
                session_id=self.session_id,
                run_id=self.run_id,
                sequence=self.sequence,
            )
        )


@dataclass(slots=True)
class DertekRuntime:
    agent: Agent
    sessions: SessionStore
    events: ContextualEventSink

    @property
    def session(self) -> Session:
        return self.agent.session

    async def run(self, prompt: str) -> AgentRunResult:
        run_id = self.events.begin(self.session.id)
        self.events.emit(AgentEvent(EventType.RUN_STARTED, "Run started", {"prompt": prompt}))
        try:
            result = await self.agent.run(prompt)
        except Exception as exc:
            self.events.emit(AgentEvent(EventType.ERROR, str(exc)))
            raise
        else:
            self.events.emit(
                AgentEvent(EventType.RUN_FINISHED, "Run finished", {"steps": result.steps})
            )
            return result
        finally:
            self.sessions.save(self.session)
            del run_id


def build_runtime(
    workspace: Path,
    *,
    provider_name: str | None = None,
    openai_auth: OpenAIAuthMode | str | None = None,
    model: str | None = None,
    small_model: str | None = None,
    large_model: str | None = None,
    approval_mode: ApprovalMode | str | None = None,
    session_id: str | None = None,
    events: EventSink | None = None,
    approval_handler: ApprovalHandler = deny_approval,
    paths: AppPaths | None = None,
) -> DertekRuntime:
    workspace = workspace.expanduser().resolve()
    store = SessionStore(paths)
    settings = load_settings(store.paths)
    if provider_name:
        settings = settings.model_copy(update={"provider": provider_name})
    if openai_auth:
        settings = settings.model_copy(update={"openai_auth": OpenAIAuthMode(openai_auth)})
    if model:
        settings = settings.model_copy(update={"model": model})
    if small_model:
        settings = settings.model_copy(update={"small_model": small_model})
    if large_model:
        settings = settings.model_copy(update={"large_model": large_model, "model": None})
    if approval_mode:
        settings = settings.model_copy(update={"approval_mode": ApprovalMode(approval_mode)})

    if session_id:
        session = store.load(session_id)
        if session.workspace != workspace:
            raise ValueError(
                f"Session {session_id} belongs to {session.workspace}, not workspace {workspace}"
            )
    else:
        session = Session(workspace=workspace)
    session.provider = settings.provider
    session.auth_mode = settings.openai_auth.value if settings.provider == "openai" else None
    session.model = settings.effective_large_model

    contextual_events = ContextualEventSink(events)
    provider = build_provider(
        settings.provider, openai_auth=settings.openai_auth, paths=store.paths
    )
    if hasattr(provider, "validate_model"):
        provider.validate_model(settings.small_model)
        provider.validate_model(settings.effective_large_model)
    policy = CommandPolicy()
    agent = Agent(
        settings=settings,
        provider=provider,
        router=build_router(contextual_events),
        tools=build_default_registry(
            str(workspace), timeout_seconds=settings.shell_timeout_seconds, policy=policy
        ),
        hooks=HookManager(policy, approval_mode=settings.approval_mode),
        session=session,
        events=contextual_events,
        approval_handler=approval_handler,
    )
    runtime = DertekRuntime(agent=agent, sessions=store, events=contextual_events)
    store.save(session)
    return runtime
