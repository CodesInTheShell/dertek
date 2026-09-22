from __future__ import annotations

from typing import Any

from dertek.models import ToolResult
from dertek.security.workspace import WorkspaceGuard
from dertek.tools.base import Tool
from dertek.tools.utils import truncate_text


class ListFilesTool(Tool):
    name = "list_files"
    description = "List files and directories inside the workspace with a bounded recursion depth."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_depth": {"type": "integer", "minimum": 0, "maximum": 6},
        },
        "required": ["path", "max_depth"],
        "additionalProperties": False,
    }
    ignored = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}

    def __init__(self, guard: WorkspaceGuard) -> None:
        self.guard = guard

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            base = self.guard.resolve(arguments["path"] or ".")
            max_depth = int(arguments["max_depth"])
            if not base.is_dir():
                raise NotADirectoryError(str(base))
            rows: list[str] = []
            for path in sorted(base.rglob("*")):
                rel = path.relative_to(base)
                if any(part in self.ignored for part in rel.parts):
                    continue
                depth = len(rel.parts) - 1
                if depth > max_depth:
                    continue
                suffix = "/" if path.is_dir() else ""
                rows.append(f"{rel}{suffix}")
                if len(rows) >= 1000:
                    rows.append("[listing capped at 1000 entries]")
                    break
            text, truncated = truncate_text("\n".join(rows))
            return ToolResult(call_id, self.name, text, truncated=truncated)
        except Exception as exc:
            return ToolResult(call_id, self.name, str(exc), is_error=True)
