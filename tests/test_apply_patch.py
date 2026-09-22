from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dertek.tools.apply_patch import ApplyPatchTool
from dertek.tools.internal_patch import InternalPatchEngine, PatchError, parse_patch


def run_patch(workspace: Path, patch: str):
    return asyncio.run(ApplyPatchTool(str(workspace)).execute("call-1", {"patch": patch}))


def test_dertek_multifile_add_update_delete_and_rename(tmp_path: Path) -> None:
    (tmp_path / "edit.txt").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "delete.txt").write_text("gone\n", encoding="utf-8")
    (tmp_path / "old.txt").write_text("old name\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: edit.txt
@@
 one
-two
+changed
*** Add File: nested/new.txt
+new file
*** Delete File: delete.txt
*** Update File: old.txt
*** Move to: renamed.txt
@@
-old name
+new name
*** End Patch"""

    result = run_patch(tmp_path, patch)

    assert not result.is_error, result.output
    assert "internal engine" in result.output
    assert (tmp_path / "edit.txt").read_text() == "one\nchanged\n"
    assert (tmp_path / "nested/new.txt").read_text() == "new file\n"
    assert not (tmp_path / "delete.txt").exists()
    assert not (tmp_path / "old.txt").exists()
    assert (tmp_path / "renamed.txt").read_text() == "new name\n"


def test_unified_diff_uses_internal_outside_git(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\nworld\n")
    patch = """--- a/hello.txt
+++ b/hello.txt
@@ -1,2 +1,2 @@
 hello
-world
+Dertek
"""
    result = run_patch(tmp_path, patch)
    assert not result.is_error, result.output
    assert "internal engine" in result.output
    assert (tmp_path / "hello.txt").read_text() == "hello\nDertek\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
def test_unified_diff_uses_git_without_changing_index(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    path = tmp_path / "hello.txt"
    path.write_text("hello\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True)
    before = subprocess.run(
        ["git", "diff", "--cached", "--binary"], cwd=tmp_path, text=True, capture_output=True, check=True
    ).stdout
    patch = """--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-hello
+hello from git
"""
    result = run_patch(tmp_path, patch)
    after = subprocess.run(
        ["git", "diff", "--cached", "--binary"], cwd=tmp_path, text=True, capture_output=True, check=True
    ).stdout
    assert not result.is_error, result.output
    assert "git engine" in result.output
    assert path.read_text() == "hello from git\n"
    assert after == before


def test_git_unavailable_routes_unified_to_internal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "file.txt").write_text("old\n")
    monkeypatch.setattr("dertek.tools.apply_patch.shutil.which", lambda _name: None)
    result = run_patch(
        tmp_path,
        "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n",
    )
    assert not result.is_error, result.output
    assert "internal engine" in result.output
    assert (tmp_path / "file.txt").read_text() == "new\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is unavailable")
def test_git_context_failure_does_not_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "file.txt").write_text("actual\n")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("internal fallback must not run")

    monkeypatch.setattr(InternalPatchEngine, "apply", forbidden)
    result = run_patch(
        tmp_path,
        "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-stale\n+new\n",
    )
    assert result.is_error
    assert "git apply --check failed" in result.output
    assert (tmp_path / "file.txt").read_text() == "actual\n"


def test_unified_add_delete_rename_and_multiple_hunks(tmp_path: Path) -> None:
    (tmp_path / "edit.txt").write_text("a\nb\nc\nd\n")
    (tmp_path / "delete.txt").write_text("delete\n")
    (tmp_path / "old.txt").write_text("rename\n")
    patch = """--- /dev/null
+++ b/nested/add.txt
@@ -0,0 +1 @@
+added
--- a/edit.txt
+++ b/edit.txt
@@ -1,2 +1,2 @@
 a
-b
+B
@@ -3,2 +3,2 @@
 c
-d
+D
--- a/delete.txt
+++ /dev/null
@@ -1 +0,0 @@
-delete
diff --git a/old.txt b/new.txt
similarity index 100%
rename from old.txt
rename to new.txt
"""
    result = run_patch(tmp_path, patch)
    assert not result.is_error, result.output
    assert (tmp_path / "nested/add.txt").read_text() == "added\n"
    assert (tmp_path / "edit.txt").read_text() == "a\nB\nc\nD\n"
    assert not (tmp_path / "delete.txt").exists()
    assert not (tmp_path / "old.txt").exists()
    assert (tmp_path / "new.txt").read_text() == "rename\n"


def test_preserves_crlf_missing_final_newline_and_permissions(tmp_path: Path) -> None:
    path = tmp_path / "script.txt"
    path.write_bytes(b"one\r\ntwo")
    path.chmod(0o750)
    patch = """--- a/script.txt
+++ b/script.txt
@@ -1,2 +1,2 @@
 one
-two
\\ No newline at end of file
+changed
\\ No newline at end of file
"""
    result = run_patch(tmp_path, patch)
    assert not result.is_error, result.output
    assert path.read_bytes() == b"one\r\nchanged"
    assert path.stat().st_mode & 0o777 == 0o750


@pytest.mark.parametrize(
    "patch",
    [
        "*** Begin Patch\n*** Add File: ../escape.txt\n+x\n*** End Patch",
        "*** Begin Patch\n*** Add File: /tmp/escape.txt\n+x\n*** End Patch",
        "GIT binary patch\nliteral 0\n",
        "--- a/file.txt\n+++ b/file.txt\n@@ malformed\n-old\n+new\n",
    ],
)
def test_rejects_unsafe_or_malformed_patches(tmp_path: Path, patch: str) -> None:
    (tmp_path / "file.txt").write_text("old\n")
    result = run_patch(tmp_path, patch)
    assert result.is_error


def test_rejects_symlink_and_rename_collision(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside\n")
    os.symlink(outside, tmp_path / "link.txt")
    symlink = run_patch(
        tmp_path,
        "*** Begin Patch\n*** Update File: link.txt\n@@\n-outside\n+changed\n*** End Patch",
    )
    assert symlink.is_error
    assert outside.read_text() == "outside\n"

    (tmp_path / "source.txt").write_text("source\n")
    (tmp_path / "target.txt").write_text("target\n")
    collision = run_patch(
        tmp_path,
        "*** Begin Patch\n*** Update File: source.txt\n*** Move to: target.txt\n*** End Patch",
    )
    assert collision.is_error


def test_stale_context_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("actual\n")
    result = run_patch(
        tmp_path,
        "*** Begin Patch\n*** Update File: file.txt\n@@\n-stale\n+new\n*** End Patch",
    )
    assert result.is_error
    assert path.read_text() == "actual\n"


def test_mid_write_failure_rolls_back_files_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.txt"
    first.write_text("before\n")
    plan = parse_patch(
        "*** Begin Patch\n"
        "*** Update File: first.txt\n@@\n-before\n+after\n"
        "*** Add File: nested/second.txt\n+new\n"
        "*** End Patch"
    )
    engine = InternalPatchEngine(tmp_path)
    original_write = engine._atomic_write
    calls = 0

    def fail_second(path: Path, data: bytes, mode: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected failure")
        original_write(path, data, mode)

    monkeypatch.setattr(engine, "_atomic_write", fail_second)
    with pytest.raises(PatchError, match="rolled back"):
        engine.apply(plan)
    assert first.read_text() == "before\n"
    assert not (tmp_path / "nested").exists()
    assert not list(tmp_path.rglob("*.tmp"))
