from __future__ import annotations

import asyncio
import subprocess
from typing import Any

from dertek.models import ToolResult
from dertek.tools.base import Tool
from dertek.tools.utils import truncate_text


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show the current git diff for the workspace."
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def __init__(self, workspace: str) -> None:
        self.workspace = workspace

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        del arguments

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", "diff", "--no-ext-diff"],
                cwd=self.workspace,
                text=True,
                capture_output=True,
                check=False,
            )

        try:
            completed = await asyncio.to_thread(run)
            output = completed.stdout or completed.stderr or "No diff."
            output, truncated = truncate_text(output)
            return ToolResult(
                call_id,
                self.name,
                output,
                is_error=completed.returncode != 0,
                truncated=truncated,
            )
        except Exception as exc:
            return ToolResult(call_id, self.name, str(exc), is_error=True)
