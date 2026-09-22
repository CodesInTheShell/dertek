# Dertek CLI

Dertek is an experimental agentic coding CLI built around a **two-speed architecture**:

- **TypeSafe Jev** handles fast, bounded decisions such as task routing.
- A **generative LLM** handles reasoning, code generation, debugging, and final responses.
- Deterministic Python code handles tools, workspace boundaries, policy checks, events, and execution.

`dertek-cli` is intentionally only an interface. The reusable agent lives behind the UI-neutral `dertek.runtime` assembly layer, so a future `dertek-desktop` can reuse the same runtime instead of reimplementing the agent or copying CLI setup.

## Status

This repository is a runnable v0.1 foundation, not a hardened production sandbox. OpenAI is implemented now. Anthropic Claude and Google Gemini are represented in the provider abstraction and are planned, but not implemented yet.

## Quick start

```bash
uv sync
export OPENAI_API_KEY="..."
export TYPESAFE_API_KEY="..."   # optional but recommended
uv run dertek
```

One-shot usage:

```bash
uv run dertek "find the User model and explain it"
uv run dertek "run the tests and explain any failures"
```

## Local state and sessions

Dertek creates owner-only local state at `~/.dertek/`:

```text
~/.dertek/
├── settings.json       # non-secret defaults
└── sessions/
    └── <session-id>.json
```

Every CLI invocation creates a persisted session. The session file contains the workspace, provider continuation state, prompts, responses, tool calls, approval decisions, and raw tool output so a future desktop can restore the complete timeline. Treat it as sensitive local data. API keys are never saved there.

```bash
uv run dertek --session <session-id>
uv run dertek sessions list
uv run dertek sessions delete <session-id>
```

Configuration priority is CLI flags, then `DERTEK_*` environment variables (and `.env` for development), then `~/.dertek/settings.json`, then built-in defaults. Keep `OPENAI_API_KEY` and `TYPESAFE_API_KEY` in environment variables or an OS credential store, never in `settings.json`.

Useful commands:

```bash
uv run dertek doctor
uv run dertek version
uv run dertek --help
```

## Router behavior

When `TYPESAFE_API_KEY` is configured, Dertek uses TypeSafe Jev to classify the prompt into:

- `chat`
- `code`
- `debug`
- `search`
- `command`

Confidence gates are applied by Dertek itself:

- **High confidence**: use the route strongly and expose a focused tool set.
- **Medium confidence**: treat the route as a hint and let the main LLM verify it naturally.
- **Low confidence**: do not constrain the main LLM with the route.

If TypeSafe is not configured or temporarily fails, Dertek falls back to a small deterministic heuristic router so the CLI remains usable.

## Current tools

- `read_file`
- `list_files`
- `search_files`
- `shell`
- `apply_patch`
- `git_diff`

`apply_patch` currently uses `git apply`, so editing works best inside a Git repository.

## Security model

v0.1 provides workspace path guards, deterministic command policy checks, and user approval for shell commands that are not verified as direct read-only commands. It is **not an OS sandbox**. See [`docs/security.md`](docs/security.md) before using Dertek on sensitive machines or repositories.

## Documentation

Start with:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/router.md`](docs/router.md)
- [`docs/providers.md`](docs/providers.md)
- [`docs/security.md`](docs/security.md)
- [`docs/development.md`](docs/development.md)
- [`docs/desktop-roadmap.md`](docs/desktop-roadmap.md)

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

## Why direct Responses API?

Dertek deliberately owns its agent loop, tool dispatch, state, hooks, and routing. This keeps the architecture provider-neutral and gives us a clean place to integrate Jev decisions before and after expensive model calls.
