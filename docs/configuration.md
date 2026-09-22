# Configuration

Dertek is a Python 3.12+ application. The recommended installation and runtime workflow uses `uv`; see the [README prerequisites](../README.md#prerequisites) or the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

## First-run creation

Installing Dertek with `uv tool install .` does not create user configuration. Dertek creates the owner-only `~/.dertek/` directory and `settings.json` the first time an installed command initializes local state, for example:

```bash
dertek doctor
dertek
dertek sessions list
```

The resulting layout is:

```text
~/.dertek/
├── settings.json
└── sessions/
```

## Default settings

`~/.dertek/settings.json` contains non-secret application defaults. A complete default configuration is:

```json
{
  "provider": "openai",
  "small_model": "gpt-5.6-luna",
  "small_reasoning_effort": "high",
  "large_model": "gpt-5.6-terra",
  "large_reasoning_effort": "low",
  "router_high_confidence": 0.9,
  "router_medium_confidence": 0.65,
  "max_steps": 12,
  "max_jev_calls_per_turn": 4,
  "small_model_step_limit": 2,
  "jev_verification_enabled": true,
  "shell_timeout_seconds": 120,
  "approval_mode": "on-request"
}
```

Jev chooses the initial tier and may escalate Luna to Terra after meaningful tool evidence. A confident small decision uses Luna/high. Large, uncertain, unavailable-Jev, and heuristic-fallback decisions use Terra/low. The Jev call ceiling reserves one intake, up to two checkpoints, and optional verification.

Valid reasoning effort values for the default models are `none`, `low`, `medium`, `high`, `xhigh`, and `max`.

## Configuration precedence

From highest to lowest priority:

1. CLI options such as `--provider`, `--small-model`, `--large-model`, and the legacy `--model` large-model override.
2. `DERTEK_*` environment variables. Contributors may also supply these with `uv run --env-file .env`.
3. `~/.dertek/settings.json`.
4. Built-in defaults.

Equivalent environment variables include:

```env
DERTEK_PROVIDER=openai
DERTEK_SMALL_MODEL=gpt-5.6-luna
DERTEK_SMALL_REASONING_EFFORT=high
DERTEK_LARGE_MODEL=gpt-5.6-terra
DERTEK_LARGE_REASONING_EFFORT=low
DERTEK_ROUTER_HIGH_CONFIDENCE=0.90
DERTEK_ROUTER_MEDIUM_CONFIDENCE=0.65
DERTEK_MAX_STEPS=12
DERTEK_MAX_JEV_CALLS_PER_TURN=4
DERTEK_SMALL_MODEL_STEP_LIMIT=2
DERTEK_JEV_VERIFICATION_ENABLED=true
DERTEK_SHELL_TIMEOUT_SECONDS=120
DERTEK_APPROVAL_MODE=on-request
```

Use `dertek doctor` to see the active provider, model tiers, reasoning efforts, and credential status.

## Credentials

Never put API keys in `settings.json`. Keep them in `.env`, exported environment variables, or an OS credential store:

```env
OPENAI_API_KEY=your_openai_api_key
TYPESAFE_API_KEY=your_typesafe_api_key
```

When working from the source checkout, run with the local file explicitly:

```bash
uv run --env-file .env dertek doctor
uv run --env-file .env dertek
```

`OPENAI_API_KEY` is required for the implemented provider. `TYPESAFE_API_KEY` enables Jev; without it, Dertek uses its heuristic router and conservatively selects the large model.

For a globally installed uv tool, export credentials in the shell or use an OS credential manager. The installed command does not automatically read `.env` from the Dertek source clone while running in another project.

## Provider support

`openai` is the only implemented provider in v0.1. The `anthropic` and `gemini` values are reserved for future adapters and currently raise a not-implemented error.
