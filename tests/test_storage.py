import json
import stat
from pathlib import Path

import pytest

from dertek.core.session import Session, ToolRecord
from dertek.exceptions import ConfigurationError
from dertek.runtime.storage import AppPaths, SessionStore, load_settings


def test_session_round_trip_preserves_full_history_and_permissions(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "home" / ".dertek")
    store = SessionStore(paths)
    session = Session(workspace=tmp_path / "workspace", provider="openai", model="test-model")
    turn = session.begin_turn("inspect the repository")
    turn.route = {"route": "search", "confidence": 0.99}
    turn.tools.append(ToolRecord("read_file", {"path": "secret.txt"}, "call-1", output="raw output"))
    turn.response = "Done"
    store.save(session)

    restored = store.load(session.id)
    assert restored.to_dict() == session.to_dict()
    assert stat.S_IMODE(paths.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(paths.settings_file.stat().st_mode) == 0o600
    assert stat.S_IMODE((paths.sessions_dir / f"{session.id}.json").stat().st_mode) == 0o600


def test_corrupt_and_missing_sessions_raise_clear_errors(tmp_path: Path) -> None:
    store = SessionStore(AppPaths(tmp_path / ".dertek"))
    with pytest.raises(ConfigurationError, match="not found"):
        store.load("a" * 32)
    store.ensure()
    broken = store.paths.sessions_dir / ("b" * 32 + ".json")
    broken.write_text("not-json", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="invalid JSON"):
        store.load("b" * 32)


def test_environment_overrides_json_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    store = SessionStore(paths)
    store.ensure()
    paths.settings_file.write_text(json.dumps({"model": "json-model", "max_steps": 4}), encoding="utf-8")
    monkeypatch.setenv("DERTEK_MODEL", "environment-model")
    settings = load_settings(paths)
    assert settings.model == "environment-model"
    assert settings.max_steps == 4


def test_settings_file_contains_no_credentials(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    SessionStore(paths).ensure()
    data = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert not any("key" in key.lower() or "secret" in key.lower() for key in data)
