<p align="center">
  <img src="dertek-logo.png" alt="Dertek logo" width="320">
</p>

# Dertek CLI

**Author:** dantebytes

Dertek is an experimental agentic coding CLI built around a **two-speed architecture**:

- **TypeSafe Jev** handles fast, bounded decisions such as task routing.
- A **generative LLM** handles reasoning, code generation, debugging, and final responses.
- Deterministic Python code handles tools, workspace boundaries, policy checks, events, and execution.

`dertek-cli` is intentionally only an interface. The reusable agent lives behind the UI-neutral `dertek.runtime` assembly layer, so a future `dertek-desktop` can reuse the same runtime instead of reimplementing the agent or copying CLI setup.

## Status

This repository is a runnable v0.1 foundation, not a hardened production sandbox. OpenAI is implemented now. Anthropic Claude and Google Gemini are represented in the provider abstraction and are planned, but not implemented yet.

## Prerequisites

Dertek is a Python 3.12+ application. [`uv`](https://docs.astral.sh/uv/getting-started/installation/) is the recommended Python project and dependency manager because this repository uses `pyproject.toml` and `uv.lock`.

Install `uv` with Astral's official standalone installer.

macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart the terminal if the installer updates your `PATH`, then verify:

```bash
uv --version
```

Package-manager alternatives include `brew install uv` on macOS and `winget install --id=astral-sh.uv -e` on Windows. See the official installation page for additional methods.

## Install Dertek

```bash
git clone https://github.com/CodesInTheShell/dertek.git
cd dertek
uv tool install .
dertek version
```

For the first installation, use `uv tool install .` as shown above. After updating an existing clone, reinstall with `--force` so the currently installed Dertek tool is replaced:

```bash
cd /path/to/dertek
git pull
uv tool install --force .
dertek version
```

If `dertek` is not found, run `uv tool list` first. If Dertek is absent, run `uv tool install .` from the clone. If it is installed but not discoverable, run `uv tool update-shell` and restart the terminal. The update-shell command configures `PATH`; it does not install Dertek. See the [installation guide](docs/installation.md) for detailed troubleshooting, updating, editable installs, and removal.

Export credentials through your shell or use an OS credential manager:

```bash
export OPENAI_API_KEY="your-openai-key"
export TYPESAFE_API_KEY="your-typesafe-key"
dertek doctor
```

`OPENAI_API_KEY` is required for the coding model. `TYPESAFE_API_KEY` enables Jev routing; without it, Dertek uses its heuristic router. Do not put either key in `~/.dertek/settings.json`. An installed tool does not automatically read the `.env` file in the Dertek source clone when launched from another project.

## Use Dertek in a project

Run Dertek from the project you want it to work on:

```bash
cd /path/to/another-project
export OPENAI_API_KEY="your-openai-key"
export TYPESAFE_API_KEY="your-typesafe-key"
dertek
```

The current directory becomes the workspace. Alternatively, use `--workspace` or `-C` without changing directories:

```bash
dertek -C /path/to/another-project "explain this project"
```

Configure the two LLM tiers in `.env` or `~/.dertek/settings.json`:

```env
DERTEK_SMALL_MODEL=gpt-5.6-luna
DERTEK_SMALL_REASONING_EFFORT=high
DERTEK_LARGE_MODEL=gpt-5.6-terra
DERTEK_LARGE_REASONING_EFFORT=low
```

The equivalent `~/.dertek/settings.json` fields are `"small_model"`, `"small_reasoning_effort"`, `"large_model"`, and `"large_reasoning_effort"`.

Dertek deliberately gives Luna `high` reasoning for inexpensive small tasks and Terra `low` reasoning for the main large-task path. The Responses API field is `reasoning: {"effort": "..."}`; valid Terra/Luna values are `none`, `low`, `medium`, `high`, `xhigh`, and `max`.

Jev selects `small` for narrow, well-defined, low-risk requests and `large` for coding, debugging, modification, ambiguous, or multi-step work. A missing Jev key or low-confidence model decision always falls back to the large model. The original `DERTEK_MODEL` and `--model` remain supported as legacy large-model overrides.

One-shot usage:

```bash
dertek "find the User model and explain it"
dertek "run the tests and explain any failures"
```

## Local state and sessions

Dertek creates owner-only local state at `~/.dertek/`:

```text
~/.dertek/
├── settings.json       # non-secret defaults
└── sessions/
    └── <session-id>.json
```

Installation alone does not create this directory. The first command that initializes local state—such as `dertek doctor`, `dertek`, or `dertek sessions list`—creates it. Each agent invocation creates a persisted session. The session file contains the workspace, provider continuation state, prompts, responses, tool calls, approval decisions, and raw tool output so a future desktop can restore the complete timeline. Treat it as sensitive local data. API keys are never saved there.

```bash
dertek --session <session-id>
dertek sessions list
dertek sessions delete <session-id>
```

Configuration priority is CLI flags, then `DERTEK_*` environment variables, then `~/.dertek/settings.json`, then built-in defaults. API credentials are separate: pass `.env` with `uv run --env-file .env ...`, export the keys in your shell, or use an OS credential store. Never put API keys in `settings.json`.

See [`docs/configuration.md`](docs/configuration.md) for the complete default JSON, environment-variable mapping, first-run behavior, and provider support.

Useful commands:

```bash
dertek doctor
dertek version
dertek --help
```

## Router behavior

When `TYPESAFE_API_KEY` is configured, Jev controls bounded decisions while Luna and Terra perform generative work. Intake selects the route, workflow, tool profile, model tier, and verification level in one batched request. Event-driven checkpoints may escalate Luna to Terra after failures, mutations, scope expansion, or the small-model step limit. Final verification runs only when it can change the outcome. Routes are:

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

Dertek makes at most four Jev calls per turn: one intake, up to two meaningful checkpoints, and optional verification. Successful routine read-only tools do not add Jev calls. Jev decisions never replace deterministic security policy.

## Current tools

- `read_file`
- `list_files`
- `search_files`
- `shell`
- `apply_patch`
- `git_diff`

`apply_patch` is Git-independent. It accepts standard unified diffs and Dertek
`*** Begin Patch` blocks. Unified diffs use `git apply --check` followed by
`git apply` when the workspace is a Git worktree; all Dertek patches, non-Git
workspaces, and environments without Git use the internal UTF-8 text patcher.
Neither path stages files or creates commits.

## Security model

v0.1 provides workspace path guards, deterministic command policy checks, and user approval for shell commands that are not verified as direct read-only commands. It is **not an OS sandbox**. See [`docs/security.md`](docs/security.md) before using Dertek on sensitive machines or repositories.

## Documentation

Start with:

- [`docs/installation.md`](docs/installation.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/configuration.md`](docs/configuration.md)
- [`docs/router.md`](docs/router.md)
- [`docs/providers.md`](docs/providers.md)
- [`docs/security.md`](docs/security.md)
- [`docs/development.md`](docs/development.md)
- [`docs/desktop-roadmap.md`](docs/desktop-roadmap.md)

## Development

The global tool installation is for normal use. Contributors should use the repository environment:

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```

## Why direct Responses API?

Dertek deliberately owns its agent loop, tool dispatch, state, hooks, and routing. This keeps the architecture provider-neutral and gives us a clean place to integrate Jev decisions before and after expensive model calls.
