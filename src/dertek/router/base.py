from __future__ import annotations

from pathlib import Path
from typing import Protocol

from dertek.router.models import RouteDecision


class Router(Protocol):
    async def route(self, prompt: str, workspace: Path) -> RouteDecision: ...
