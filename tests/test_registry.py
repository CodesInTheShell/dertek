from pathlib import Path

import pytest

from dertek.router.models import ConfidenceBand, RouteResolution, TaskRoute, ToolProfile
from dertek.tools.registry import build_default_registry
from dertek.tools.shell import ShellTool


def test_high_search_route_focuses_tools(tmp_path: Path) -> None:
    registry = build_default_registry(str(tmp_path))
    resolution = RouteResolution(TaskRoute.SEARCH, 0.99, ConfidenceBand.HIGH, True)
    names = {schema["name"] for schema in registry.schemas_for_resolution(resolution)}
    assert names == {"read_file", "list_files", "search_files", "git_diff"}


def test_trusted_tool_profiles_are_bounded(tmp_path: Path) -> None:
    registry = build_default_registry(str(tmp_path))
    assert registry.schemas_for_profile(ToolProfile.NONE, trusted=True) == []
    editing = {schema["name"] for schema in registry.schemas_for_profile(ToolProfile.EDITING, trusted=True)}
    assert editing == {"read_file", "list_files", "search_files", "apply_patch", "git_diff"}
    untrusted = {schema["name"] for schema in registry.schemas_for_profile(ToolProfile.NONE, trusted=False)}
    assert "shell" in untrusted and "apply_patch" in untrusted


@pytest.mark.asyncio
async def test_shell_tool_directly_refuses_deterministic_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_run(*args, **kwargs):
        del args, kwargs
        raise AssertionError("subprocess must not run for a denied command")

    monkeypatch.setattr("dertek.tools.shell.subprocess.run", unexpected_run)
    result = await ShellTool(str(tmp_path)).execute(
        "dangerous-1", {"command": "sudo reboot"}
    )

    assert result.is_error is True
    assert "dangerous-command rule" in result.output
