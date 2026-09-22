# LLM providers

## Contract

The core depends only on `LLMProvider`:

```python
class LLMProvider(Protocol):
    async def generate(self, request: AgentRequest) -> AgentResponse: ...
```

Provider-specific SDK objects do not escape the provider package.

## OpenAI

`OpenAIProvider` uses the Responses API and custom function tools. Tool calls are normalized into Dertek's `ToolCall` model. OpenAI response IDs are returned as opaque continuation tokens so the core can continue a multi-step turn without knowing OpenAI internals.

Environment:

```bash
export OPENAI_API_KEY="..."
```

The default model is configurable with:

```bash
export DERTEK_MODEL="gpt-5.5"
```

or per command:

```bash
uv run dertek --model gpt-5.5
```

## Claude and Gemini

The provider enum already reserves `anthropic` and `gemini`. Their factories currently raise a clear `ProviderNotImplementedError`.

When those providers are added, the desired rule is that **the core should not change**. New code should live mainly in:

```text
src/dertek/providers/anthropic.py
src/dertek/providers/gemini.py
```

Any provider-specific continuation mechanism should be translated to/from the generic `continuation_token` or handled internally by that provider.
