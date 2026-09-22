from __future__ import annotations

from dertek.router.models import ConfidenceBand, IntakeDecision, RouteResolution

BASE_INSTRUCTIONS = """You are Dertek, an agentic coding assistant operating inside a local workspace.

Work carefully and use tools when repository facts are needed. Prefer inspecting relevant files before editing. Keep changes focused on the user's request. After edits, inspect the diff and run appropriate tests when practical. Never claim a command or test ran unless a tool result confirms it.

You may only work inside the configured workspace. Tool security and approvals are enforced outside the model, so do not attempt to bypass them.
"""


ROUTE_INSTRUCTIONS = {
    "chat": "The request is likely explanatory. Avoid unnecessary tool calls, but inspect files when the answer depends on repository-specific facts.",
    "code": "The request likely requires code changes. Inspect before editing, make minimal changes, review the diff, and test when practical.",
    "debug": "The request likely concerns a failure. Reproduce or inspect evidence first, form a diagnosis, then make and verify the smallest useful fix.",
    "search": "The request is likely repository discovery. Prefer list/search/read tools before considering changes.",
    "command": "The user likely asked to execute something. Use the shell tool when appropriate and report the observed result accurately.",
}


def build_instructions(workspace: str, resolution: RouteResolution) -> str:
    route_line = ""
    if resolution.apply_as_constraint and resolution.route is not None:
        route_line = f"\nRouting signal: {ROUTE_INSTRUCTIONS[resolution.route.value]}\n"
    elif resolution.route is not None:
        route_line = (
            f"\nWeak routing hint ({resolution.confidence:.2f} confidence): "
            f"{resolution.route.value}. Treat this only as a hint and verify from the user's request.\n"
        )

    return BASE_INSTRUCTIONS + f"\nWorkspace: {workspace}\n" + route_line


def build_decision_instructions(workspace: str, decision: IntakeDecision, *, trusted: bool) -> str:
    if not trusted:
        return build_instructions(
            workspace,
            RouteResolution(decision.route, decision.confidence, ConfidenceBand.MEDIUM, False),
        )
    return (
        BASE_INSTRUCTIONS
        + f"\nWorkspace: {workspace}\n"
        + f"Jev workflow: route={decision.route.value}, intent={decision.intent.value}, "
        + f"complexity={decision.complexity.value}, risk={decision.risk.value}, "
        + f"scope={decision.scope.value}, workflow={decision.workflow.value}, "
        + f"verification={decision.verification.value}. Follow this bounded workflow, "
        + "but rely on observed repository evidence and deterministic tool policy.\n"
    )
