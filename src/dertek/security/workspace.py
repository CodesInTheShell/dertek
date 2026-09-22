from __future__ import annotations

from pathlib import Path

from dertek.exceptions import WorkspaceViolationError


class WorkspaceGuard:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def resolve(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        candidate = path if path.is_absolute() else self.workspace / path
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise WorkspaceViolationError(
                f"Path escapes workspace: {raw_path}"
            ) from exc
        return candidate
