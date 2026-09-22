from __future__ import annotations

from typing import Any

from dertek.models import ToolResult
from dertek.security.workspace import WorkspaceGuard
from dertek.tools.base import Tool
from dertek.tools.utils import truncate_text


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace, optionally by line range."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace."},
            "start_line": {"type": ["integer", "null"], "minimum": 1},
            "end_line": {"type": ["integer", "null"], "minimum": 1},
        },
        "required": ["path", "start_line", "end_line"],
        "additionalProperties": False,
    }

    def __init__(self, guard: WorkspaceGuard) -> None:
        self.guard = guard

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            path = self.guard.resolve(arguments["path"])
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            start = arguments.get("start_line") or 1
            end = arguments.get("end_line") or len(lines)
            if end < start:
                raise ValueError("end_line must be greater than or equal to start_line")
            selected = lines[start - 1 : end]
            rendered = "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start=start))
            rendered, truncated = truncate_text(rendered)
            return ToolResult(call_id, self.name, rendered, truncated=truncated)
        except Exception as exc:
            return ToolResult(call_id, self.name, str(exc), is_error=True)
