from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dertek.models import ToolCall, ToolResult
from dertek.security.policy import CommandPolicy


@dataclass(frozen=True, slots=True)
class HookDecision:
    action: Literal["allow", "ask", "deny"]
    reason: str


class HookManager:
    def __init__(self, policy: CommandPolicy, approval_mode: str = "on-request") -> None:
        self.policy = policy
        self.approval_mode = approval_mode

    async def pre_tool(self, call: ToolCall) -> HookDecision:
        if call.name == "shell":
            command = str(call.arguments.get("command", ""))
            decision = self.policy.evaluate_shell(command, self.approval_mode)
            return HookDecision(decision.action, decision.reason)

        # apply_patch validates all paths and constrains both patch engines to the workspace.
        # Read/search/diff tools are non-destructive.
        return HookDecision("allow", "Allowed by tool policy")

    async def post_tool(self, call: ToolCall, result: ToolResult) -> ToolResult:
        del call
        return result
