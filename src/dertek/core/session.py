from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class ToolRecord:
    name: str
    arguments: dict[str, Any]
    call_id: str
    started_at: str = field(default_factory=utc_now)
    output: str | None = None
    is_error: bool | None = None
    truncated: bool | None = None
    approval_reason: str | None = None
    approved: bool | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class SessionTurn:
    prompt: str
    started_at: str = field(default_factory=utc_now)
    route: dict[str, Any] | None = None
    model: str | None = None
    model_tier: str | None = None
    reasoning_effort: str | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    model_transitions: list[dict[str, Any]] = field(default_factory=list)
    jev_call_count: int = 0
    verification_status: str | None = None
    tools: list[ToolRecord] = field(default_factory=list)
    response: str | None = None
    error: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class Session:
    workspace: Path
    id: str = field(default_factory=lambda: uuid4().hex)
    continuation_token: str | None = None
    turns: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    provider: str | None = None
    model: str | None = None
    history: list[SessionTurn] = field(default_factory=list)

    def reset_provider_context(self) -> None:
        self.continuation_token = None

    def begin_turn(self, prompt: str) -> SessionTurn:
        turn = SessionTurn(prompt=prompt)
        self.history.append(turn)
        self.updated_at = turn.started_at
        return turn

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 2,
            "id": self.id,
            "workspace": str(self.workspace),
            "continuation_token": self.continuation_token,
            "turns": self.turns,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provider": self.provider,
            "model": self.model,
            "history": [asdict(turn) for turn in self.history],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Session:
        try:
            history = [
                SessionTurn(
                    prompt=str(turn["prompt"]),
                    started_at=str(turn["started_at"]),
                    route=turn.get("route"),
                    model=turn.get("model"),
                    model_tier=turn.get("model_tier"),
                    reasoning_effort=turn.get("reasoning_effort"),
                    decisions=list(turn.get("decisions", [])),
                    model_transitions=list(turn.get("model_transitions", [])),
                    jev_call_count=int(turn.get("jev_call_count", 0)),
                    verification_status=turn.get("verification_status"),
                    tools=[ToolRecord(**tool) for tool in turn.get("tools", [])],
                    response=turn.get("response"),
                    error=turn.get("error"),
                    finished_at=turn.get("finished_at"),
                )
                for turn in value.get("history", [])
            ]
            return cls(
                workspace=Path(value["workspace"]).resolve(),
                id=str(value["id"]),
                continuation_token=value.get("continuation_token"),
                turns=int(value.get("turns", 0)),
                created_at=str(value["created_at"]),
                updated_at=str(value["updated_at"]),
                provider=value.get("provider"),
                model=value.get("model"),
                history=history,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid Dertek session file") from exc
