from pathlib import Path

from dertek.router.models import ConfidenceBand, RouteResolution, TaskRoute, ToolProfile
from dertek.tools.registry import build_default_registry


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
