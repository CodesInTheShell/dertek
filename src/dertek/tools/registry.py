from __future__ import annotations

from dertek.models import ToolCall, ToolResult
from dertek.router.models import ConfidenceBand, RouteResolution, TaskRoute
from dertek.security.policy import CommandPolicy
from dertek.security.workspace import WorkspaceGuard
from dertek.tools.apply_patch import ApplyPatchTool
from dertek.tools.base import Tool
from dertek.tools.git_diff import GitDiffTool
from dertek.tools.list_files import ListFilesTool
from dertek.tools.read_file import ReadFileTool
from dertek.tools.search_files import SearchFilesTool
from dertek.tools.shell import ShellTool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def schemas_for_resolution(self, resolution: RouteResolution) -> list[dict[str, object]]:
        if resolution.band != ConfidenceBand.HIGH or resolution.route is None:
            names = set(self._tools)
        else:
            focused = {
                TaskRoute.CHAT: {"read_file", "list_files", "search_files", "git_diff"},
                TaskRoute.SEARCH: {"read_file", "list_files", "search_files", "git_diff"},
                TaskRoute.COMMAND: {"read_file", "list_files", "search_files", "shell", "git_diff"},
                TaskRoute.CODE: set(self._tools),
                TaskRoute.DEBUG: set(self._tools),
            }
            names = focused[resolution.route]
        return [self._tools[name].schema() for name in sorted(names)]

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(call.id, call.name, f"Unknown tool: {call.name}", is_error=True)
        return await tool.execute(call.id, call.arguments)

    @staticmethod
    def denied_result(call: ToolCall, reason: str) -> ToolResult:
        return ToolResult(call.id, call.name, reason, is_error=True)


def build_default_registry(
    workspace: str, timeout_seconds: int = 120, policy: CommandPolicy | None = None
) -> ToolRegistry:
    guard = WorkspaceGuard(__import__("pathlib").Path(workspace))
    return ToolRegistry(
        [
            ReadFileTool(guard),
            ListFilesTool(guard),
            SearchFilesTool(guard),
            ShellTool(workspace, timeout_seconds=timeout_seconds, policy=policy),
            ApplyPatchTool(workspace),
            GitDiffTool(workspace),
        ]
    )
