# Desktop roadmap

The desktop application should consume Dertek Core rather than invoke terminal parsing or scrape CLI output.

## Already prepared in v0.1

- UI-neutral `Agent` class
- callback-based structured `AgentEvent` stream with run/session identifiers and sequencing
- provider abstraction
- router abstraction
- explicit approval handler
- persisted, serializable session transcript and provider continuation metadata
- structured tool calls and results

## Suggested desktop boundary

```text
Desktop UI
   |
   +--> submit(prompt)
   +--> approve(request)
   +--> cancel(run)
   |
   <--- AgentEvent stream
   <--- final AgentRunResult
```

## Likely desktop features

- repository/workspace picker
- conversation/session sidebar
- diff viewer
- approval modal
- tool timeline
- model/provider selector
- router diagnostics with confidence display
- settings and API key storage

Before building the desktop shell, add cancellation, a stable event schema version, and durable reconstruction of ChatGPT's normalized `store: false` replay buffer when resuming after a process restart. The desktop should call `dertek.runtime.build_runtime()` with its own event callback and approval handler; it must not invoke or scrape the CLI.
