# Security

Dertek v0.1 is an experimental coding agent. It is **not a hardened sandbox**.

## What v0.1 does

1. File tools pass through `WorkspaceGuard` and cannot intentionally resolve outside the configured workspace.
2. Obvious destructive shell patterns such as `sudo`, `rm -rf /`, `mkfs`, shutdown/reboot commands, and fork bombs are denied by deterministic policy.
3. Only parsed, direct read-only commands are automatically allowed. Shell syntax, compound commands, test/build commands, `find`, redirects, substitutions, pipes, and executable hooks require approval.
4. Shell commands not recognized as direct read-only commands are sent to the approval handler in `on-request` mode.
5. `apply_patch` pre-validates every path before using either Git or the internal engine. It rejects absolute paths, traversal, workspace escapes, symlink paths, binary patches, mode-only changes, and conflicting operations.
6. The internal patch engine validates every file and hunk before writing. It uses same-directory temporary files, atomic replacement, and best-effort full rollback if a multi-file write fails.

## What v0.1 does not do

- no container, VM, seccomp, namespace, or OS-level sandbox
- no network isolation
- no secret redaction
- no filesystem syscall interception
- no guarantee that an allowed shell command cannot have side effects

A command executed with `shell=True` has the same OS permissions as the user running Dertek.

## Patch safety and Git

Editing does not require a Git repository or Git executable. Dertek-format patches always use the internal UTF-8 text engine. Standard unified diffs use `git apply --check` followed by `git apply` only inside a detected Git worktree; otherwise they use the internal engine. A Git context/applicability failure is returned directly and is never retried through a different engine.

Neither patch engine stages files, changes the Git index, commits, or invokes executable hooks. The internal engine requires exact context and does not perform fuzzy conflict resolution. Approved shell commands remain outside this protection and are not sandboxed.

Jev may classify semantic risk, select a tool profile, or recommend escalation and verification. These signals never directly authorize commands or file access. Deterministic command policy, approvals, workspace guards, and patch validation remain authoritative when Jev is confident, uncertain, or unavailable.

## Local transcript privacy

Dertek stores full session transcripts at `~/.dertek/sessions/` with owner-only file permissions. These transcripts include raw tool output and may contain sensitive repository material. API keys are never written to session files or `~/.dertek/settings.json`.

## Approval modes

`DERTEK_APPROVAL_MODE` supports:

- `on-request`: read-only commands are allowed, unknown shell commands ask, dangerous commands are denied.
- `never`: unknown shell commands are denied rather than asking.

A future hardened version should replace or supplement the current execution layer with a real sandbox.
