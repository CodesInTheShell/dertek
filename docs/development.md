# Development

## Prerequisites

Dertek is a Python application requiring Python 3.12 or newer. The recommended workflow uses [`uv`](https://docs.astral.sh/uv/getting-started/installation/) to manage Python, the virtual environment, locked dependencies, and project commands.

Install `uv` on macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install it from Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart the terminal when necessary and verify the installation:

```bash
uv --version
```

Other officially documented options include Homebrew (`brew install uv`), WinGet (`winget install --id=astral-sh.uv -e`), and `pipx install uv`.

## User installation versus development

Normal users should clone the repository and install the CLI as an isolated user tool:

```bash
uv tool install .
```

That makes `dertek` available from unrelated project directories. See [`installation.md`](installation.md). The commands below create a repository-local development environment for contributors instead.

## Development setup

```bash
uv sync --group dev
```

Run tests:

```bash
uv run pytest
```

Lint:

```bash
uv run ruff check .
```

Run from the source environment without installing the global tool:

```bash
cp .env.example .env
# Add TYPESAFE_API_KEY and, for API-key mode, OPENAI_API_KEY.
uv run --env-file .env dertek doctor
uv run --env-file .env dertek --auth api-key
```

`OPENAI_API_KEY` is required only for API-key mode. ChatGPT-mode development uses `dertek auth login` and the owner-only credential file outside the repository. The TypeSafe key is optional but enables Jev routing. Keep API keys out of `~/.dertek/settings.json` and Git. As an alternative to `--env-file`, export the variables in the current shell before running Dertek.

For active CLI development, an optional editable tool installation reflects source changes immediately:

```bash
uv tool install --force --editable /absolute/path/to/dertek
```

For a fresh non-editable local build after source changes, use `uv cache clean dertek-cli` followed by `uv tool install --force --refresh /absolute/path/to/dertek`.

See [`configuration.md`](configuration.md) for first-run creation, the complete `settings.json` schema, precedence, and supported providers.

## Adding a tool

1. Create a `Tool` subclass in `src/dertek/tools/`.
2. Define a JSON Schema `parameters` object.
3. Implement `async execute(call_id, arguments)`.
4. Register it in `build_default_registry()`.
5. Decide which high-confidence routes should expose it.
6. Add deterministic policy checks if the tool can mutate state.
7. Add tests.

### Patch tool contract

Keep the provider-facing schema as `apply_patch(patch: string)`. The implementation accepts conventional unified diffs and the controlled Dertek format:

```text
*** Begin Patch
*** Update File: src/example.py
@@
-old text
+new text
*** End Patch
```

Use Dertek format when generating a patch specifically for Dertek. It always uses the internal engine and therefore behaves the same in Git repositories, ordinary folders, extracted archives, and machines without Git. Unified diffs use Git inside a worktree and the internal engine elsewhere. Add patch-engine tests for both routes; tests must also verify workspace containment, exact context, permissions/newlines, and rollback behavior.

## Adding a provider

Implement the `LLMProvider` protocol and normalize provider-native tool calls into `ToolCall`. Do not add provider SDK imports to `dertek.core`.

## Adding a decision engine

Implement `DecisionEngine.intake`, `checkpoint`, and `verify` with the typed models in `dertek.router.models`. Batch related bounded judgments in each request, preserve confidence/probabilities, and keep threshold policy in core code rather than the adapter. Every phase must have a conservative availability fallback.

## Testing philosophy

Unit tests should not require API keys. Use fake providers and routers to test the agent loop. Integration tests that hit OpenAI or TypeSafe can be added separately and skipped unless explicit environment variables are present.

## Developing authentication transports

Keep OpenAI authentication behind the Responses transport boundary. Persist only the non-secret `openai_auth` setting and rebuild the transport on every process start and session resume. OAuth credentials belong only in the dedicated credential store. Tests must use mocked OAuth and model endpoints, verify refresh and restart behavior, and assert that secrets never enter settings, sessions, events, diagnostics, or errors.
