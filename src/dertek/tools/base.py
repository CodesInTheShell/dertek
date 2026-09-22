from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from dertek.models import ToolResult


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    mutates_workspace: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }

    @abstractmethod
    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError
