from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Literal

PolicyAction = Literal["allow", "ask", "deny"]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyAction
    reason: str
    argv: tuple[str, ...] | None = None


class CommandPolicy:
    DANGEROUS_PATTERNS = [
        re.compile(r"(^|[;&|]\s*)sudo\b", re.I),
        re.compile(r"\brm\s+-[^\n]*r[^\n]*f[^\n]*\s+/(?:\s|$)", re.I),
        re.compile(r"\bmkfs(?:\.|\s)", re.I),
        re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.I),
        re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;\s*:", re.I),
        re.compile(r"\bdd\s+.*\bof=/dev/", re.I),
    ]

    SHELL_SYNTAX = re.compile(r"[;|&<>`$()\n\\]")
    READ_ONLY_COMMANDS = {"pwd", "ls", "rg", "grep", "cat", "head", "tail"}
    GIT_READ_ONLY_COMMANDS = {"status", "diff", "log", "show", "branch"}
    DISALLOWED_RG_OPTIONS = {"--pre", "--pre-glob"}

    def evaluate_shell(self, command: str, approval_mode: str = "on-request") -> PolicyDecision:
        stripped = command.strip()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(stripped):
                return PolicyDecision("deny", "Command matches a deterministic dangerous-command rule")

        argv = self._read_only_argv(stripped)
        if argv is not None:
            return PolicyDecision("allow", "Recognized direct read-only command", tuple(argv))

        if approval_mode == "never":
            return PolicyDecision("deny", "Command is not auto-approved and approval mode is 'never'")
        return PolicyDecision("ask", f"Shell command requires approval: {stripped}")

    def _read_only_argv(self, command: str) -> list[str] | None:
        """Return direct argv only for commands safe to run without shell interpretation."""
        if not command or self.SHELL_SYNTAX.search(command):
            return None
        try:
            argv = shlex.split(command)
        except ValueError:
            return None
        if not argv:
            return None
        executable = argv[0]
        if executable in self.READ_ONLY_COMMANDS:
            if executable == "rg" and any(arg in self.DISALLOWED_RG_OPTIONS for arg in argv[1:]):
                return None
            return argv
        if executable != "git" or len(argv) < 2:
            return None
        if argv[1] not in self.GIT_READ_ONLY_COMMANDS:
            return None
        if any(arg in {"-c", "--config-env", "--exec-path", "--ext-diff"} for arg in argv[2:]):
            return None
        return argv
