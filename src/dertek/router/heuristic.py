from __future__ import annotations

import re
from pathlib import Path

from dertek.router.models import RouteDecision, TaskRoute


class HeuristicRouter:
    """Small availability fallback. It intentionally reports modest confidence."""

    PATTERNS = [
        (TaskRoute.DEBUG, re.compile(r"\b(error|exception|traceback|failing|fails|bug|broken|debug|why.*fail)\b", re.I)),
        (TaskRoute.COMMAND, re.compile(r"\b(run|execute|build|test|pytest|npm test|uv run|git status)\b", re.I)),
        (TaskRoute.SEARCH, re.compile(r"\b(find|locate|where is|search|look for|which file)\b", re.I)),
        (TaskRoute.CODE, re.compile(r"\b(add|implement|create|change|modify|refactor|fix|edit|write|rename)\b", re.I)),
    ]

    async def route(self, prompt: str, workspace: Path) -> RouteDecision:
        del workspace
        for route, pattern in self.PATTERNS:
            if pattern.search(prompt):
                return RouteDecision(route=route, confidence=0.70, source="heuristic")
        return RouteDecision(route=TaskRoute.CHAT, confidence=0.60, source="heuristic")
