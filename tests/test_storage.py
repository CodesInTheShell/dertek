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
    turn.decisions.append({"phase": "intake", "result": {"model_tier": "small"}})
    turn.model_transitions.append({"from": "small", "to": "large"})
    turn.jev_call_count = 2
    turn.verification_status = "passed"
    store.save(session)

    restored = store.load(session.id)
    assert restored.to_dict() == session.to_dict()
    assert stat.S_IMODE(paths.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(paths.settings_file.stat().st_mode) == 0o600
    assert stat.S_IMODE((paths.sessions_dir / f"{session.id}.json").stat().st_mode) == 0o600


def test_legacy_session_loads_with_decision_defaults(tmp_path: Path) -> None:
    value = {
        "version": 1,
        "id": "a" * 32,
        "workspace": str(tmp_path),
        "turns": 1,
        "created_at": "2025-01-01T00:00:00+00:00",
        "updated_at": "2025-01-01T00:00:00+00:00",
        "history": [{"prompt": "old", "started_at": "2025-01-01T00:00:00+00:00"}],
    }
    restored = Session.from_dict(value)
    assert restored.history[0].decisions == []
    assert restored.history[0].jev_call_count == 0
    assert restored.to_dict()["version"] == 2


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
    paths.settings_file.write_text(json.dumps({"large_model": "json-model", "max_steps": 4}), encoding="utf-8")
    monkeypatch.setenv("DERTEK_LARGE_MODEL", "environment-model")
    settings = load_settings(paths)
    assert settings.large_model == "environment-model"
    assert settings.max_steps == 4


def test_auto_approval_mode_environment_overrides_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    store = SessionStore(paths)
    store.ensure()
    paths.settings_file.write_text(
        json.dumps({"approval_mode": "never"}), encoding="utf-8"
    )
    monkeypatch.setenv("DERTEK_APPROVAL_MODE", "auto")
    assert load_settings(paths).approval_mode == "auto"


def test_approval_mode_defaults_to_on_request(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    SessionStore(paths).ensure()
    assert load_settings(paths).approval_mode == "on-request"


def test_settings_file_contains_no_credentials(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    SessionStore(paths).ensure()
    data = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert not any("key" in key.lower() or "secret" in key.lower() for key in data)


def test_existing_tier_model_settings_are_preserved(
    tmp_path: Path,
) -> None:
    paths = AppPaths(tmp_path / ".dertek")
    store = SessionStore(paths)
    store.ensure()
    paths.settings_file.write_text(
        json.dumps(
            {
                "small_model": "gpt-5.6-luna",
                "large_model": "gpt-5.6-terra",
            }
        ),
        encoding="utf-8",
    )

    settings = load_settings(paths)

    assert settings.small_model == "gpt-5.6-luna"
    assert settings.large_model == "gpt-5.6-terra"
