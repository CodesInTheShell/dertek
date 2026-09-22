from pathlib import Path

import pytest

from dertek.exceptions import WorkspaceViolationError
from dertek.security.workspace import WorkspaceGuard


def test_workspace_guard_allows_inside(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path)
    assert guard.resolve("a/b.txt") == (tmp_path / "a/b.txt").resolve()


def test_workspace_guard_blocks_escape(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path)
    with pytest.raises(WorkspaceViolationError):
        guard.resolve("../outside.txt")
