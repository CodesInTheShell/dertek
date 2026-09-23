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
- no general secret redaction for arbitrary repository contents or raw tool output
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

- `on-request` (default): verified direct read-only commands run automatically; commands that may modify state or are ambiguous pause for user approval; deterministically dangerous commands are denied.
- `never`: verified direct read-only commands still run automatically, but anything that would require approval is denied instead of prompting; deterministically dangerous commands remain denied.
- `auto`: commands that would normally require approval run without prompting; deterministically dangerous commands remain denied.

Use `on-request` for interactive development, `never` for fail-closed read-only automation, and `auto` only for trusted unattended jobs that must run tests, builds, package commands, or mutations. Select a mode per run with `dertek --approval-mode on-request|never|auto`, or persist it in settings. Auto approvals are recorded in session tool history and emitted as structured `tool_auto_approved` events.

**Caution:** Auto-approved commands are not sandboxed. Complex commands execute through the system shell with the same OS permissions and credentials as the Dertek process. Prefer an isolated CI runner or container with minimal credentials and a disposable checkout. Auto mode does not bypass workspace guards, patch validation, shell timeouts, maximum steps, model/tool errors, or deterministic dangerous-command rules, and it cannot guarantee task completion.

A future hardened version should replace or supplement the current execution layer with a real sandbox.

## OAuth credential handling

ChatGPT OAuth credentials are stored separately from configuration and transcripts at `~/.dertek/auth/openai.json`. Dertek creates the containing directories with mode `0700`, writes the file atomically with mode `0600`, refreshes expiring access tokens, and persists rotated refresh tokens. Credentials and authorization headers are excluded from settings, sessions, events, diagnostics, and error bodies. Version one does not use the OS keyring, so the security of this file depends on the user's local account and home-directory protections.
