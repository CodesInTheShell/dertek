from pathlib import Path

from dertek.router.models import ConfidenceBand, RouteResolution, TaskRoute
from dertek.tools.registry import build_default_registry


def test_high_search_route_focuses_tools(tmp_path: Path) -> None:
    registry = build_default_registry(str(tmp_path))
    resolution = RouteResolution(TaskRoute.SEARCH, 0.99, ConfidenceBand.HIGH, True)
    names = {schema["name"] for schema in registry.schemas_for_resolution(resolution)}
    assert names == {"read_file", "list_files", "search_files", "git_diff"}
