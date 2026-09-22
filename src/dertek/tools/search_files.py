from __future__ import annotations

import fnmatch
from typing import Any

from dertek.models import ToolResult
from dertek.security.workspace import WorkspaceGuard
from dertek.tools.base import Tool
from dertek.tools.utils import truncate_text


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Search UTF-8 text files in the workspace for a literal string."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "path": {"type": "string"},
            "glob": {"type": "string", "description": "Filename glob such as *.py or *."},
            "max_matches": {"type": "integer", "minimum": 1, "maximum": 200},
        },
        "required": ["query", "path", "glob", "max_matches"],
        "additionalProperties": False,
    }
    ignored = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}

    def __init__(self, guard: WorkspaceGuard) -> None:
        self.guard = guard

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            base = self.guard.resolve(arguments["path"] or ".")
            query = arguments["query"]
            pattern = arguments["glob"] or "*"
            limit = int(arguments["max_matches"])
            matches: list[str] = []
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(base)
                if any(part in self.ignored for part in rel.parts):
                    continue
                if not fnmatch.fnmatch(path.name, pattern):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for number, line in enumerate(text.splitlines(), start=1):
                    if query in line:
                        matches.append(f"{rel}:{number}: {line.strip()}")
                        if len(matches) >= limit:
                            break
                if len(matches) >= limit:
                    break
            rendered = "\n".join(matches) if matches else "No matches found."
            rendered, truncated = truncate_text(rendered)
            return ToolResult(call_id, self.name, rendered, truncated=truncated)
        except Exception as exc:
            return ToolResult(call_id, self.name, str(exc), is_error=True)
