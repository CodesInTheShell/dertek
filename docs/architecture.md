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
     Router       Providers      Tools
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
Router
   |
   v
Confidence gate
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
       tool result -> LLM
```

## Package responsibilities

- `dertek.runtime`: UI-neutral construction, local settings/session storage, and contextual event callbacks.
- `dertek.cli`: Typer/Rich interface, interactive REPL, approval UI.
- `dertek.core`: agent loop, session, context building, events.
- `dertek.providers`: provider-neutral contracts and OpenAI implementation.
- `dertek.router`: TypeSafe Jev router, fallback router, confidence gates.
- `dertek.tools`: tool contracts, registry, file/search/shell/git tools.
- `dertek.hooks`: lifecycle decisions around tool execution.
- `dertek.security`: workspace path boundaries and command policy.

## State strategy

OpenAI Responses uses a continuation token (`previous_response_id`) for the current session. The provider contract exposes this as an opaque `continuation_token`, rather than leaking OpenAI-specific naming into the core. Future providers may implement this differently.

`Session` is serializable. The runtime persists full sessions under `~/.dertek/sessions/`; provider continuation state remains opaque to the core.
