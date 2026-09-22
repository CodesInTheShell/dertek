# Security

Dertek v0.1 is an experimental coding agent. It is **not a hardened sandbox**.

## What v0.1 does

1. File tools pass through `WorkspaceGuard` and cannot intentionally resolve outside the configured workspace.
2. Obvious destructive shell patterns such as `sudo`, `rm -rf /`, `mkfs`, shutdown/reboot commands, and fork bombs are denied by deterministic policy.
3. Only parsed, direct read-only commands are automatically allowed. Shell syntax, compound commands, test/build commands, `find`, redirects, substitutions, pipes, and executable hooks require approval.
4. Shell commands not recognized as direct read-only commands are sent to the approval handler in `on-request` mode.
5. `apply_patch` uses `git apply` without unsafe-path mode and is limited to the current repository/workspace.

## What v0.1 does not do

- no container, VM, seccomp, namespace, or OS-level sandbox
- no network isolation
- no secret redaction
- no filesystem syscall interception
- no guarantee that an allowed shell command cannot have side effects

A command executed with `shell=True` has the same OS permissions as the user running Dertek.

## Local transcript privacy

Dertek stores full session transcripts at `~/.dertek/sessions/` with owner-only file permissions. These transcripts include raw tool output and may contain sensitive repository material. API keys are never written to session files or `~/.dertek/settings.json`.

## Approval modes

`DERTEK_APPROVAL_MODE` supports:

- `on-request`: read-only commands are allowed, unknown shell commands ask, dangerous commands are denied.
- `never`: unknown shell commands are denied rather than asking.

A future hardened version should replace or supplement the current execution layer with a real sandbox.
