from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from typesafe_sdk import Choice, TypeSafeClient

from dertek.router.models import RouteDecision, TaskRoute


class TypeSafeJevRouter:
    def __init__(self) -> None:
        pass

    async def route(self, prompt: str, workspace: Path) -> RouteDecision:
        return await asyncio.to_thread(self._route_sync, prompt, workspace)

    @staticmethod
    def _route_sync(prompt: str, workspace: Path) -> RouteDecision:
        state = {
            "prompt": prompt,
            "workspace_name": workspace.name,
            "application": "Dertek agentic coding CLI",
        }
        criteria = {
            "chat": "Explanation, discussion, or question that does not primarily request repository modification, debugging, repository discovery, or command execution.",
            "code": "Implement, modify, refactor, create, or fix code/files in the workspace.",
            "debug": "Investigate an error, failing test, exception, bug, or unexpected behavior where diagnosis is central.",
            "search": "Locate files, symbols, definitions, usages, or repository information where discovery is central.",
            "command": "Explicitly run, execute, build, test, inspect status, or invoke a local command where execution is central.",
        }
        with TypeSafeClient() as client:
            response = client.system_one(
                state=state,
                questions={
                    "route": Choice(
                        instructions="What is the primary task type for this coding assistant request?",
                        criteria=criteria,
                    )
                },
            )

        answers: Any = getattr(response, "answers", None) or getattr(response, "choices", None)
        if answers is None:
            raise RuntimeError("TypeSafe response did not contain answers/choices")
        answer = answers["route"]
        choice = str(answer.choice)
        probabilities = dict(getattr(answer, "probabilities", {}) or {})
        confidence = getattr(answer, "confidence", None)
        if confidence is None:
            confidence = probabilities.get(choice, 0.0)

        return RouteDecision(
            route=TaskRoute(choice),
            confidence=float(confidence),
            probabilities={str(k): float(v) for k, v in probabilities.items()},
            source="typesafe-jev",
        )
