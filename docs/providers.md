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

The small and large models are configurable with:

```bash
export DERTEK_SMALL_MODEL="gpt-5.6-luna"
export DERTEK_SMALL_REASONING_EFFORT="high"
export DERTEK_LARGE_MODEL="gpt-5.6-terra"
export DERTEK_LARGE_REASONING_EFFORT="low"
```

or per command:

```bash
dertek --small-model gpt-5.6-luna --large-model gpt-5.6-terra
```

`DERTEK_MODEL` and `--model` remain backward-compatible overrides for the large model.

For Responses API calls, Dertek sends the selected tier's effort as `reasoning={"effort": value}`. Both default models support `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Defaults are Luna/high for small tasks and Terra/low for large tasks.

Official references: [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra), [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), and [Responses API create](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

## Claude and Gemini

The provider enum already reserves `anthropic` and `gemini`. Their factories currently raise a clear `ProviderNotImplementedError`.

When those providers are added, the desired rule is that **the core should not change**. New code should live mainly in:

```text
src/dertek/providers/anthropic.py
src/dertek/providers/gemini.py
```

Any provider-specific continuation mechanism should be translated to/from the generic `continuation_token` or handled internally by that provider.
