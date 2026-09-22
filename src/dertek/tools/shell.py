from __future__ import annotations

import asyncio
import subprocess
from typing import Any

from dertek.models import ToolResult
from dertek.security.policy import CommandPolicy
from dertek.tools.base import Tool
from dertek.tools.utils import truncate_text


class ShellTool(Tool):
    name = "shell"
    description = "Run a local shell command in the workspace. Commands are checked by deterministic policy before execution."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "minLength": 1},
        },
        "required": ["command"],
        "additionalProperties": False,
    }
    mutates_workspace = True

    def __init__(
        self, workspace: str, timeout_seconds: int = 120, policy: CommandPolicy | None = None
    ) -> None:
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds
        self.policy = policy or CommandPolicy()

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        command = arguments["command"]
        decision = self.policy.evaluate_shell(command)

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                list(decision.argv) if decision.action == "allow" and decision.argv else command,
                shell=decision.argv is None,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )

        try:
            completed = await asyncio.to_thread(run)
            output = ""
            if completed.stdout:
                output += completed.stdout
            if completed.stderr:
                output += ("\n" if output else "") + completed.stderr
            output += f"\n[exit code: {completed.returncode}]"
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
