from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from dertek.models import ToolResult
from dertek.tools.base import Tool
from dertek.tools.internal_patch import InternalPatchEngine, PatchError, PatchFormat, parse_patch
from dertek.tools.utils import truncate_text


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = (
        "Apply a unified diff or Dertek '*** Begin Patch' block. Uses git apply for "
        "unified diffs in Git worktrees and a Git-independent internal engine otherwise."
    )
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
        self.workspace = Path(workspace).resolve()

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        patch = arguments["patch"]
        try:
            output = self._execute_sync(patch)
            output, truncated = truncate_text(output)
            return ToolResult(call_id, self.name, output, truncated=truncated)
        except Exception as exc:
            output, truncated = truncate_text(str(exc))
            return ToolResult(call_id, self.name, output, is_error=True, truncated=truncated)

    def _execute_sync(self, patch: str) -> str:
        plan = parse_patch(patch)
        internal = InternalPatchEngine(self.workspace)
        internal.validate_paths(plan)
        if plan.format == PatchFormat.DERTEK:
            changed = internal.apply(plan)
            return self._success("internal", changed)

        git = shutil.which("git")
        if git and self._is_git_worktree(git):
            self._git_apply(git, patch)
            return self._success("git", plan.changed_paths)

        changed = internal.apply(plan)
        return self._success("internal", changed)

    def _is_git_worktree(self, git: str) -> bool:
        result = subprocess.run(
            [git, "rev-parse", "--is-inside-work-tree"],
            cwd=self.workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _git_apply(self, git: str, patch: str) -> None:
        for check_only in (True, False):
            command = [git, "apply", "--whitespace=nowarn"]
            if check_only:
                command.append("--check")
            result = subprocess.run(
                command,
                input=patch,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                phase = "git apply --check" if check_only else "git apply"
                detail = result.stderr.strip() or result.stdout.strip() or f"{phase} failed"
                raise PatchError(f"{phase} failed: {detail}")

    @staticmethod
    def _success(engine: str, paths: list[str]) -> str:
        return f"Applied patch with {engine} engine: {', '.join(paths)}"
