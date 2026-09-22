# Development

## Setup

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

Run locally:

```bash
export OPENAI_API_KEY="..."
export TYPESAFE_API_KEY="..."
uv run dertek
```

## Adding a tool

1. Create a `Tool` subclass in `src/dertek/tools/`.
2. Define a JSON Schema `parameters` object.
3. Implement `async execute(arguments)`.
4. Register it in `build_default_registry()`.
5. Decide which high-confidence routes should expose it.
6. Add deterministic policy checks if the tool can mutate state.
7. Add tests.

## Adding a provider

Implement the `LLMProvider` protocol and normalize provider-native tool calls into `ToolCall`. Do not add provider SDK imports to `dertek.core`.

## Adding a router

Implement `Router.route(prompt, workspace)` and return `RouteDecision`. Keep thresholds in `RouterThresholds`, not inside the adapter.

## Testing philosophy

Unit tests should not require API keys. Use fake providers and routers to test the agent loop. Integration tests that hit OpenAI or TypeSafe can be added separately and skipped unless explicit environment variables are present.
