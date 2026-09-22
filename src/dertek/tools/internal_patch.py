from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

from dertek.security.workspace import WorkspaceGuard


class PatchError(ValueError):
    pass


class PatchFormat(StrEnum):
    DERTEK = "dertek"
    UNIFIED = "unified"


class OperationKind(StrEnum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    RENAME = "rename"


@dataclass(slots=True)
class Hunk:
    old_start: int | None
    lines: list[tuple[str, str]] = field(default_factory=list)
    new_final_newline: bool | None = None


@dataclass(slots=True)
class PatchOperation:
    kind: OperationKind
    source: str | None
    target: str | None
    hunks: list[Hunk] = field(default_factory=list)
    added_lines: list[str] | None = None
    added_final_newline: bool = True

    @property
    def paths(self) -> list[str]:
        return list(dict.fromkeys(path for path in (self.source, self.target) if path))


@dataclass(slots=True)
class PatchPlan:
    format: PatchFormat
    operations: list[PatchOperation]

    @property
    def changed_paths(self) -> list[str]:
        return list(dict.fromkeys(path for operation in self.operations for path in operation.paths))


@dataclass(slots=True)
class _Snapshot:
    exists: bool
    data: bytes | None = None
    mode: int | None = None


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def detect_patch_format(patch: str) -> PatchFormat:
    stripped = patch.lstrip("\ufeff\r\n")
    if stripped.startswith("*** Begin Patch"):
        return PatchFormat.DERTEK
    if stripped.startswith(("diff --git ", "--- ")):
        return PatchFormat.UNIFIED
    raise PatchError("Patch must be a unified diff or a '*** Begin Patch' block")


def parse_patch(patch: str) -> PatchPlan:
    patch_format = detect_patch_format(patch)
    if patch_format == PatchFormat.DERTEK:
        return _parse_dertek(patch)
    return _parse_unified(patch)


def _clean_path(raw: str, *, strip_git_prefix: bool = False) -> str:
    value = raw.strip()
    if "\t" in value:
        value = value.split("\t", 1)[0]
    if value.startswith('"') or value.endswith('"'):
        raise PatchError("Quoted patch paths are not supported")
    if value == "/dev/null":
        return value
    if strip_git_prefix and value.startswith(("a/", "b/")):
        value = value[2:]
    path = PurePosixPath(value)
    if not value or value == "." or path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise PatchError(f"Unsafe patch path: {raw}")
    return path.as_posix()


def _parse_hunks(lines: list[str], index: int, *, dertek: bool) -> tuple[list[Hunk], int]:
    hunks: list[Hunk] = []
    while index < len(lines) and lines[index].startswith("@@"):
        header = lines[index]
        match = _HUNK_HEADER.match(header)
        if not match and not dertek:
            raise PatchError(f"Malformed unified hunk header: {header}")
        old_start = int(match.group(1)) if match else None
        old_count = int(match.group(2) or "1") if match else None
        new_count = int(match.group(4) or "1") if match else None
        old_seen = 0
        new_seen = 0
        hunk = Hunk(old_start=old_start)
        index += 1
        previous_prefix: str | None = None
        while index < len(lines):
            line = lines[index]
            if (
                not dertek
                and old_seen == old_count
                and new_seen == new_count
                and line != r"\ No newline at end of file"
            ):
                break
            if line.startswith("@@") or line.startswith("diff --git "):
                break
            if dertek and line.startswith("*** "):
                break
            if line == r"\ No newline at end of file":
                if previous_prefix in {"+", " "}:
                    hunk.new_final_newline = False
                elif previous_prefix == "-":
                    hunk.new_final_newline = True
                else:
                    raise PatchError("No-newline marker has no preceding patch line")
                index += 1
                continue
            if not line or line[0] not in {" ", "+", "-"}:
                raise PatchError(f"Malformed patch hunk line: {line}")
            previous_prefix = line[0]
            hunk.lines.append((line[0], line[1:]))
            if line[0] in {" ", "-"}:
                old_seen += 1
            if line[0] in {" ", "+"}:
                new_seen += 1
            if not dertek and (old_seen > old_count or new_seen > new_count):
                raise PatchError(f"Hunk line counts exceed its header: {header}")
            index += 1
        if not hunk.lines:
            raise PatchError("Patch hunk cannot be empty")
        if not dertek and (old_seen != old_count or new_seen != new_count):
            raise PatchError(f"Hunk line counts do not match its header: {header}")
        hunks.append(hunk)
    return hunks, index


def _parse_dertek(patch: str) -> PatchPlan:
    lines = patch.splitlines()
    if not lines or lines[0].lstrip("\ufeff") != "*** Begin Patch":
        raise PatchError("Dertek patch must start with '*** Begin Patch'")
    operations: list[PatchOperation] = []
    index = 1
    while index < len(lines):
        line = lines[index]
        if line == "*** End Patch":
            if index != len(lines) - 1:
                raise PatchError("Unexpected content after '*** End Patch'")
            break
        if line.startswith("*** Add File: "):
            target = _clean_path(line.removeprefix("*** Add File: "))
            index += 1
            content: list[str] = []
            final_newline = True
            while index < len(lines) and not lines[index].startswith("*** "):
                current = lines[index]
                if current == r"\ No newline at end of file":
                    final_newline = False
                elif not current.startswith("+"):
                    raise PatchError("Added-file lines must start with '+'")
                else:
                    content.append(current[1:])
                index += 1
            operations.append(
                PatchOperation(
                    OperationKind.ADD,
                    None,
                    target,
                    added_lines=content,
                    added_final_newline=final_newline,
                )
            )
            continue
        if line.startswith("*** Delete File: "):
            source = _clean_path(line.removeprefix("*** Delete File: "))
            operations.append(PatchOperation(OperationKind.DELETE, source, None))
            index += 1
            continue
        if line.startswith("*** Update File: "):
            source = _clean_path(line.removeprefix("*** Update File: "))
            target = source
            index += 1
            if index < len(lines) and lines[index].startswith("*** Move to: "):
                target = _clean_path(lines[index].removeprefix("*** Move to: "))
                index += 1
            hunks, index = _parse_hunks(lines, index, dertek=True)
            if not hunks and target == source:
                raise PatchError(f"Update has no hunks: {source}")
            kind = OperationKind.RENAME if target != source else OperationKind.UPDATE
            operations.append(PatchOperation(kind, source, target, hunks=hunks))
            continue
        raise PatchError(f"Unknown Dertek patch directive: {line}")
    else:
        raise PatchError("Dertek patch is missing '*** End Patch'")
    if not operations:
        raise PatchError("Patch contains no file operations")
    return PatchPlan(PatchFormat.DERTEK, operations)


def _parse_unified(patch: str) -> PatchPlan:
    lines = patch.splitlines()
    operations: list[PatchOperation] = []
    index = 0
    pending_rename: tuple[str, str] | None = None
    while index < len(lines):
        line = lines[index]
        if line.startswith(("GIT binary patch", "Binary files ")):
            raise PatchError("Binary patches are not supported")
        if line.startswith(("old mode ", "new mode ")):
            raise PatchError("File-mode patches are not supported")
        if line.startswith("diff --git "):
            if pending_rename:
                operations.append(
                    PatchOperation(OperationKind.RENAME, pending_rename[0], pending_rename[1])
                )
                pending_rename = None
            index += 1
            rename_from: str | None = None
            rename_to: str | None = None
            while index < len(lines) and not lines[index].startswith(("diff --git ", "--- ")):
                metadata = lines[index]
                if metadata.startswith(("GIT binary patch", "Binary files ")):
                    raise PatchError("Binary patches are not supported")
                if metadata.startswith(("old mode ", "new mode ")):
                    raise PatchError("File-mode patches are not supported")
                if metadata.startswith("rename from "):
                    rename_from = _clean_path(metadata.removeprefix("rename from "))
                elif metadata.startswith("rename to "):
                    rename_to = _clean_path(metadata.removeprefix("rename to "))
                index += 1
            if bool(rename_from) != bool(rename_to):
                raise PatchError("Rename metadata must contain both source and target")
            if rename_from and rename_to:
                pending_rename = (rename_from, rename_to)
            continue
        if line.startswith("--- "):
            if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
                raise PatchError("Unified file header is missing its +++ line")
            old_raw = _clean_path(line[4:], strip_git_prefix=True)
            new_raw = _clean_path(lines[index + 1][4:], strip_git_prefix=True)
            index += 2
            hunks, index = _parse_hunks(lines, index, dertek=False)
            if not hunks:
                raise PatchError("Unified file change contains no hunks")
            if old_raw == "/dev/null":
                operation = PatchOperation(OperationKind.ADD, None, new_raw, hunks=hunks)
            elif new_raw == "/dev/null":
                operation = PatchOperation(OperationKind.DELETE, old_raw, None, hunks=hunks)
            else:
                source, target = pending_rename or (old_raw, new_raw)
                kind = OperationKind.RENAME if source != target else OperationKind.UPDATE
                operation = PatchOperation(kind, source, target, hunks=hunks)
            operations.append(operation)
            pending_rename = None
            continue
        index += 1
    if pending_rename:
        operations.append(PatchOperation(OperationKind.RENAME, pending_rename[0], pending_rename[1]))
    if not operations:
        raise PatchError("Unified diff contains no supported file operations")
    return PatchPlan(PatchFormat.UNIFIED, operations)


class InternalPatchEngine:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.guard = WorkspaceGuard(self.workspace)

    def apply(self, plan: PatchPlan) -> list[str]:
        resolved = self._resolve_operations(plan.operations)
        mutations = self._build_mutations(resolved)
        self._commit(mutations)
        return plan.changed_paths

    def validate_paths(self, plan: PatchPlan) -> None:
        self._resolve_operations(plan.operations, content_checks=False)

    def _safe_path(self, raw: str, *, must_exist: bool = False) -> Path:
        path = self.guard.resolve(raw)
        relative = PurePosixPath(raw)
        current = self.workspace
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise PatchError(f"Patch paths may not traverse symlinks: {raw}")
        if must_exist and not path.exists():
            raise PatchError(f"Patch source does not exist: {raw}")
        if path.exists() and not path.is_file():
            raise PatchError(f"Patch path is not a regular file: {raw}")
        return path

    def _resolve_operations(
        self, operations: list[PatchOperation], *, content_checks: bool = True
    ) -> list[tuple[PatchOperation, Path | None, Path | None]]:
        resolved: list[tuple[PatchOperation, Path | None, Path | None]] = []
        touched: set[Path] = set()
        for operation in operations:
            source = self._safe_path(operation.source, must_exist=content_checks) if operation.source else None
            target = self._safe_path(operation.target) if operation.target else None
            operation_paths = {path for path in (source, target) if path is not None}
            conflicts = operation_paths & touched
            if conflicts:
                conflict = next(iter(conflicts))
                raise PatchError(f"Patch contains duplicate/conflicting path: {conflict}")
            if source:
                touched.add(source)
            if target:
                touched.add(target)
            if content_checks:
                if operation.kind == OperationKind.ADD and target and target.exists():
                    raise PatchError(f"Patch target already exists: {operation.target}")
                if operation.kind == OperationKind.RENAME and target and target.exists() and target != source:
                    raise PatchError(f"Rename target already exists: {operation.target}")
            resolved.append((operation, source, target))
        return resolved

    @staticmethod
    def _read_text(path: Path) -> tuple[list[str], str, bool, int]:
        data = path.read_bytes()
        if b"\x00" in data:
            raise PatchError(f"Binary file is not supported: {path}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PatchError(f"File is not valid UTF-8: {path}") from exc
        newline = "\r\n" if "\r\n" in text else "\n"
        final_newline = text.endswith(("\n", "\r"))
        return text.splitlines(), newline, final_newline, stat.S_IMODE(path.stat().st_mode)

    @staticmethod
    def _apply_hunks(
        original: list[str], hunks: list[Hunk], final_newline: bool
    ) -> tuple[list[str], bool]:
        current = list(original)
        offset = 0
        cursor = 0
        for hunk in hunks:
            expected = [text for prefix, text in hunk.lines if prefix in {" ", "-"}]
            replacement = [text for prefix, text in hunk.lines if prefix in {" ", "+"}]
            if hunk.old_start is not None:
                position = max(hunk.old_start - 1, 0) + offset
                if current[position : position + len(expected)] != expected:
                    raise PatchError(f"Patch context does not match at old line {hunk.old_start}")
            else:
                matches = [
                    index
                    for index in range(cursor, len(current) - len(expected) + 1)
                    if current[index : index + len(expected)] == expected
                ]
                if len(matches) != 1:
                    raise PatchError("Dertek hunk context must match exactly once")
                position = matches[0]
            current[position : position + len(expected)] = replacement
            offset += len(replacement) - len(expected)
            cursor = position + len(replacement)
            if hunk.new_final_newline is not None:
                final_newline = hunk.new_final_newline
        return current, final_newline

    def _build_mutations(
        self, resolved: list[tuple[PatchOperation, Path | None, Path | None]]
    ) -> dict[Path, tuple[bytes | None, int | None]]:
        mutations: dict[Path, tuple[bytes | None, int | None]] = {}
        for operation, source, target in resolved:
            if operation.kind == OperationKind.ADD:
                assert target is not None
                if operation.added_lines is not None:
                    lines = operation.added_lines
                    final = operation.added_final_newline
                else:
                    lines, final = self._apply_hunks([], operation.hunks, True)
                text = "\n".join(lines) + ("\n" if final else "")
                mutations[target] = (text.encode(), 0o644)
                continue
            assert source is not None
            lines, newline, final, mode = self._read_text(source)
            if operation.kind == OperationKind.DELETE:
                if operation.hunks:
                    remaining, _ = self._apply_hunks(lines, operation.hunks, final)
                    if remaining:
                        raise PatchError(f"Delete patch does not remove all content: {operation.source}")
                mutations[source] = (None, None)
                continue
            assert target is not None
            updated, final = self._apply_hunks(lines, operation.hunks, final)
            text = newline.join(updated) + (newline if final else "")
            if target != source:
                mutations[source] = (None, None)
            mutations[target] = (text.encode(), mode)
        return mutations

    @staticmethod
    def _atomic_write(path: Path, data: bytes, mode: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _commit(self, mutations: dict[Path, tuple[bytes | None, int | None]]) -> None:
        snapshots = {
            path: _Snapshot(
                exists=path.exists(),
                data=path.read_bytes() if path.exists() else None,
                mode=stat.S_IMODE(path.stat().st_mode) if path.exists() else None,
            )
            for path in mutations
        }
        existing_directories = {
            parent
            for path in mutations
            for parent in [path.parent, *path.parents]
            if parent.exists() and parent.is_relative_to(self.workspace)
        }
        try:
            for path, (data, mode) in mutations.items():
                if data is None:
                    path.unlink(missing_ok=False)
                else:
                    self._atomic_write(path, data, mode or 0o644)
        except Exception as exc:
            rollback_errors: list[str] = []
            for path, snapshot in reversed(snapshots.items()):
                try:
                    if snapshot.exists:
                        assert snapshot.data is not None and snapshot.mode is not None
                        self._atomic_write(path, snapshot.data, snapshot.mode)
                    else:
                        path.unlink(missing_ok=True)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{path}: {rollback_exc}")
            created_directories = {
                parent
                for path in mutations
                for parent in [path.parent, *path.parents]
                if parent.is_relative_to(self.workspace) and parent not in existing_directories
            }
            for directory in sorted(created_directories, key=lambda item: len(item.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            detail = f"Patch write failed and changes were rolled back: {exc}"
            if rollback_errors:
                detail += "; rollback errors: " + "; ".join(rollback_errors)
            raise PatchError(detail) from exc
