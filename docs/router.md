# Jev decision controller

Jev is Dertek's typed decision controller. Luna and Sol remain the generative workers that explain, reason, write code, and produce patches. Jev never authorizes a dangerous action or generates free-form agent work.

## Three decision phases

One Jev request batches several `Choice` judgments for each phase:

1. **Intake** always runs once and selects route, intent, complexity, risk, expected scope, workflow, tool profile, model tier, and verification level.
2. **Checkpoint** runs only when new evidence could change execution: a tool error, mutation, scope expansion, or Luna reaching its bounded step limit.
3. **Verification** runs when requested by the workflow or when the turn mutated files or retained errors. Straightforward chat and successful read-only discovery skip it.

Dertek allows at most four decision calls per turn: one intake, two checkpoints, and one verification. Routine successful read-only tool calls do not cause checkpoints.

## Model control

Jev chooses Luna for bounded generative work and Sol for complex, risky, broad, or ambiguous work. A Luna choice must meet the medium confidence threshold. Otherwise Dertek starts Sol.

Luna may escalate to Sol after a checkpoint. Dertek never downgrades Sol during a turn. Escalation clears the model-specific continuation token and gives Sol a structured handoff containing the original request, decisions, and bounded tool evidence.

Default profiles remain:

```text
small  gpt-6-luna  reasoning effort: high
large  gpt-6-sol   reasoning effort: low
```

## Confidence and tools

Default thresholds are high `0.90` and medium `0.65`. A focused tool profile is enforced only when both the overall route and tool-profile judgment are highly confident. Uncertain decisions expose the recovery tool set and favor Sol. Every Jev answer, probability, confidence, checkpoint trigger, model transition, and verification result is stored in the session timeline.

## Fallback and security

If the TypeSafe key is absent or any Jev phase fails, the heuristic decision engine handles that phase conservatively. It selects Sol, preserves recovery tools, and does not terminate the run.

Security-critical behavior remains deterministic. Command denial, user approval, workspace guards, and patch validation do not trust Jev as an authorization boundary.
