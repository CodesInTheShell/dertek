from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dertek.config import Settings
from dertek.core.session import Session
from dertek.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path

    @classmethod
    def default(cls) -> AppPaths:
        return cls(Path.home() / ".dertek")

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @property
    def auth_dir(self) -> Path:
        return self.root / "auth"

    @property
    def openai_auth_file(self) -> Path:
        return self.auth_dir / "openai.json"


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    """Write owner-only JSON without exposing a partially-written file."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _default_settings() -> dict[str, Any]:
    return {
        name: field.default
        for name, field in Settings.model_fields.items()
        if field.default is not None
    }


class SessionStore:
    """Owner-only JSON persistence for a user's local Dertek sessions."""

    _SESSION_ID = re.compile(r"^[a-f0-9]{32}$")

    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or AppPaths.default()

    def ensure(self) -> None:
        self.paths.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.paths.root.chmod(0o700)
        self.paths.sessions_dir.mkdir(mode=0o700, exist_ok=True)
        self.paths.sessions_dir.chmod(0o700)
        if not self.paths.settings_file.exists():
            self._write_json(self.paths.settings_file, _default_settings())

    def _path_for(self, session_id: str) -> Path:
        if not self._SESSION_ID.fullmatch(session_id):
            raise ConfigurationError("Session ID must be a 32-character hexadecimal value")
        return self.paths.sessions_dir / f"{session_id}.json"

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        write_json_atomic(path, value)

    def save(self, session: Session) -> None:
        self.ensure()
        self._write_json(self._path_for(session.id), session.to_dict())

    def load(self, session_id: str) -> Session:
        self.ensure()
        path = self._path_for(session_id)
        try:
            with path.open(encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Session not found: {session_id}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"Session file is invalid JSON: {session_id}") from exc
        if not isinstance(value, dict):
            raise ConfigurationError(f"Session file is invalid: {session_id}")
        try:
            return Session.from_dict(value)
        except ValueError as exc:
            raise ConfigurationError(f"Session file is invalid: {session_id}") from exc

    def list(self) -> list[Session]:
        self.ensure()
        sessions: list[Session] = []
        for path in self.paths.sessions_dir.glob("*.json"):
            try:
                sessions.append(self.load(path.stem))
            except ConfigurationError:
                continue
        return sorted(sessions, key=lambda session: session.updated_at, reverse=True)

    def delete(self, session_id: str) -> None:
        self.ensure()
        path = self._path_for(session_id)
        if not path.exists():
            raise ConfigurationError(f"Session not found: {session_id}")
        path.unlink()


def load_settings(paths: AppPaths | None = None) -> Settings:
    """Load JSON defaults, then apply dotenv/environment settings over them."""
    paths = paths or AppPaths.default()
    store = SessionStore(paths)
    store.ensure()
    try:
        with paths.settings_file.open(encoding="utf-8") as handle:
            saved = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {paths.settings_file}") from exc
    if not isinstance(saved, dict):
        raise ConfigurationError(f"Settings must be a JSON object: {paths.settings_file}")

    # Migrate the original single-model file setting in memory. An explicit new
    # large_model value wins when both keys are present. DERTEK_MODEL remains an
    # environment-level compatibility override below.
    if "model" in saved and "large_model" not in saved:
        # gpt-5.5 was written automatically by the v0.1 defaults. Let that exact
        # value migrate to the new Terra default; preserve any custom legacy ID.
        if saved["model"] != "gpt-5.5":
            saved["large_model"] = saved["model"]
    saved.pop("model", None)

    allowed = set(Settings.model_fields)
    unknown = set(saved) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigurationError(f"Unknown setting(s) in {paths.settings_file}: {names}")
    try:
        json_defaults = Settings(**saved)
        environment = Settings()
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc

    merged = json_defaults.model_dump()
    for field in environment.model_fields_set:
        merged[field] = getattr(environment, field)
    return Settings(**merged)


def update_saved_settings(paths: AppPaths | None = None, **updates: Any) -> Settings:
    """Persist non-secret settings without copying environment values."""
    paths = paths or AppPaths.default()
    SessionStore(paths).ensure()
    try:
        with paths.settings_file.open(encoding="utf-8") as handle:
            saved = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {paths.settings_file}") from exc
    if not isinstance(saved, dict):
        raise ConfigurationError(f"Settings must be a JSON object: {paths.settings_file}")
    unknown = set(updates) - set(Settings.model_fields)
    if unknown:
        raise ConfigurationError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    candidate = {**saved, **updates}
    try:
        validated = Settings(**candidate)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc
    write_json_atomic(paths.settings_file, candidate)
    return validated
