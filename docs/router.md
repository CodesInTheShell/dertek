# Router and confidence gates

Dertek uses the router only for bounded semantic decisions. It does not ask Jev to write code or perform open-ended reasoning.

## Routes

```text
chat     explanations and general questions
code     implementation/refactoring/edit requests
debug    diagnosis of failures or broken behavior
search   repository discovery and locating symbols/files
command  explicit request to run commands/tests/builds
```

## TypeSafe Jev

The adapter uses the official `typesafe-sdk` and asks one `Choice` question with the prompt as state. A `Choice` answer provides the selected option plus probabilities/confidence. The synchronous SDK call is moved to a worker thread so the rest of Dertek remains asynchronous.

## Threshold policy

Default thresholds:

```text
>= 0.90        HIGH
0.65 - 0.899   MEDIUM
< 0.65         LOW
```

The behavior is intentionally conservative:

- HIGH: the route is trusted enough to focus the available tool set and instructions.
- MEDIUM: the route is only a hint. All tools remain available so the main LLM can verify the situation itself.
- LOW: the route is effectively ignored for constraints. The main LLM receives the normal tool set.

This means an uncertain fast model never blocks the stronger model from recovering.

## Fallback

If `TYPESAFE_API_KEY` is missing or the Jev request fails, `HeuristicRouter` returns a deterministic best-effort route with deliberately modest confidence. The fallback is for availability, not quality parity with Jev.

## Future router uses

The same `Router` protocol can later drive:

- model selection
- context retrieval strategy
- token budgets
- pre-tool risk classification as an additional signal
- post-tool error classification
- deciding whether repository search should happen before the main LLM call

Security-critical authorization must remain deterministic even if semantic routing is added.
