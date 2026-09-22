from __future__ import annotations

import asyncio
import subprocess
from typing import Any

from dertek.models import ToolResult
from dertek.tools.base import Tool
from dertek.tools.utils import truncate_text


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = "Apply a unified diff to files in the current Git workspace using git apply."
    parameters = {
        "type": "object",
        "properties": {
            "patch": {"type": "string", "minLength": 1},
        },
        "required": ["patch"],
        "additionalProperties": False,
    }
    mutates_workspace = True

    def __init__(self, workspace: str) -> None:
        self.workspace = workspace

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        patch = arguments["patch"]

        def run_git_apply(check_only: bool) -> subprocess.CompletedProcess[str]:
            cmd = ["git", "apply", "--whitespace=nowarn"]
            if check_only:
                cmd.append("--check")
            return subprocess.run(
                cmd,
                input=patch,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                check=False,
            )

        try:
            checked = await asyncio.to_thread(run_git_apply, True)
            if checked.returncode != 0:
                msg, truncated = truncate_text(checked.stderr or checked.stdout or "git apply --check failed")
                return ToolResult(call_id, self.name, msg, is_error=True, truncated=truncated)
            applied = await asyncio.to_thread(run_git_apply, False)
            output = applied.stdout or applied.stderr or "Patch applied successfully."
            output, truncated = truncate_text(output)
            return ToolResult(
                call_id,
                self.name,
                output,
                is_error=applied.returncode != 0,
                truncated=truncated,
            )
        except Exception as exc:
            return ToolResult(call_id, self.name, str(exc), is_error=True)
