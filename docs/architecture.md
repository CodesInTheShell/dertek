# Architecture

## Design rule

**Dertek Core is the agent. The CLI is only a client of the core.**

```text
                 dertek-cli
                     |
                     | future
              dertek-desktop
                     |
                     v
             Dertek Runtime
                     |
                Dertek Core
       +-------------+-------------+
       |             |             |
 Decision engine  Providers      Tools
       |             |             |
   TypeSafe Jev   OpenAI now    Python code
                  Claude later
                  Gemini later
```

The runtime owns application assembly: settings, session persistence, providers, router, tools, hooks, callbacks, and approvals. The core never prints terminal UI directly. It emits `AgentEvent` objects. Each runtime event has a session ID, run ID, and monotonic sequence number. The CLI renders them with Rich; a desktop can subscribe to the same callback and render cards, timelines, approvals, diffs, and progress indicators.

## Request flow

```text
User prompt
   |
   v
Jev intake (workflow / tools / model / verification)
   |
   v
Context builder
   |
   v
LLM provider
   |
   +---- final text ------> user
   |
   +---- tool call
             |
             v
         pre-tool hook
             |
             v
      deterministic policy
             |
       allow / ask / deny
             |
             v
            tool
             |
             v
        post-tool hook
             |
             v
       tool result
             |
             +--> meaningful change -> Jev checkpoint
             |                         |
             |                         +--> continue / Luna -> Terra
             |
             +--> routine success ----> LLM
                                       |
                                       +--> optional Jev verification
```

## Package responsibilities

- `dertek.runtime`: UI-neutral construction, local settings/session storage, and contextual event callbacks.
- `dertek.cli`: Typer/Rich interface, interactive REPL, approval UI.
- `dertek.core`: agent loop, session, context building, events.
- `dertek.providers`: provider-neutral contracts and OpenAI implementation.
- `dertek.router`: typed intake/checkpoint/verification decisions, TypeSafe Jev adapter, fallback engine, and confidence gates.
- `dertek.tools`: tool contracts, registry, file/search/shell/git tools.
- `dertek.hooks`: lifecycle decisions around tool execution, including ask/deny/auto-approve policy metadata.
- `dertek.security`: workspace path boundaries and command policy.

## State strategy

API-key mode uses the public Responses API continuation token (`previous_response_id`), exposed to the core as an opaque `continuation_token`. ChatGPT mode sends `store: false`, so its transport instead replays normalized input/output items locally and never submits an unusable server continuation ID. A Luna-to-Terra escalation clears model-specific context and constructs a provider-neutral evidence handoff so state never crosses tiers.

`Session` is serializable. The runtime persists prompts, final responses, decisions, tool calls/results, approvals, model metadata, and continuation metadata under `~/.dertek/sessions/`. The saved transcript restores the UI timeline. In v0.1, ChatGPT's normalized provider replay buffer is process-local, so resuming a saved session after restarting Dertek does not yet recreate the model's complete prior context; durable provider-state reconstruction remains desktop-readiness work.

## Patch engine

`apply_patch(patch: string)` is a stable tool boundary and does not depend on Git. The tool parses and validates the complete patch before selecting an engine:

```text
Dertek patch                         -> internal engine
Unified diff + Git worktree          -> git apply
Unified diff + non-Git/no executable -> internal engine
```

The internal engine handles UTF-8 add, update, delete, and rename operations. It validates exact hunk context in memory and commits changes through atomic replacements with rollback. Git remains an optional enhancement for compatible unified diffs and for the separate `git_diff` tool.

## OpenAI authentication boundary

Runtime construction selects an OpenAI Responses transport. API-key authentication targets the public API; ChatGPT authentication targets the Codex Responses backend. Authentication, refresh, structured `store: false` replay, and streaming event normalization remain inside the provider package. Dertek handles text deltas, completed output items, tool calls, incomplete responses, and failures without requiring the Codex CLI. The core agent, Jev controller, tools, approvals, sessions, and UI event boundary are unchanged.
