# ADR-0008: Guard JSONata field extraction against undefined (no tool use)

## Status
Accepted

## Context
After resolving IAM (ADR-0006), the inference-profile requirement
(ADR-0006), and the tool-spec format issue (ADR-0007), the first
execution to actually reach Bedrock successfully still failed, one step
later:

`States.QueryEvaluationError: An error occurred while executing the state
'Reason (Bedrock Converse)'. The JSONata expression
'$states.result.Output.Message.Content[ToolUse][0].ToolUse' specified for
the field 'Output/tool_use' returned nothing (undefined).`



The `reason` task's `outputs` block extracts a `tool_use` field by
filtering the response's `Content` array for a `ToolUse` block. This
expression assumes a `ToolUse` block always exists. It does not: for a
simple query the model can answer directly (e.g. basic arithmetic), Nova
Lite may respond with plain text and `stop_reason: "end_turn"`, with no
`ToolUse` content block at all a legitimate, expected response shape
this loop must handle, not an error condition.

Step Functions' JSONata evaluation treats a field expression that
resolves to `undefined` as a hard state-execution error, rather than
silently producing `null` unlike JSONPath mode, which is more permissive
about missing fields. The original expression did not account for this.

## Decision
Wrap the `tool_use` extraction in a JSONata existence check, so a missing
`ToolUse` block produces `null` instead of failing the state:

```python
"tool_use": (
    "{% $exists($states.result.Output.Message.Content[ToolUse][0].ToolUse) "
    "? $states.result.Output.Message.Content[ToolUse][0].ToolUse : null %}"
),
```

This is safe with the existing `Choice` state's condition
(`stop_reason = 'tool_use' and iteration < max_iterations`): when there is
no tool use, `stop_reason` is not `"tool_use"`, so the `Finalize` branch is
taken and `tool_use` (now `null`) is never read.

## Rejected Alternatives

**1. Force the model to always call the tool, avoiding the no-tool-use
case entirely.**
Rejected. This would misrepresent what a ReAct loop actually needs to
handle a real agent must be able to answer directly when a tool isn't
needed. Forcing tool use to dodge this bug would hide a real, expected
response shape rather than handle it.

**2. Catch the error with a Step Functions `Catch` clause on the `Reason`
state, retrying or failing gracefully instead of fixing the expression.**
Rejected. This treats a predictable, legitimate response shape (no tool
use) as an exceptional failure to recover from, rather than a normal case
to extract correctly. A `Catch` clause is the right tool for genuine
failures (throttling, malformed responses) not for a value that is
absent by design.

## Consequences
- The `Reason` state's output now correctly represents "no tool
  requested" as `tool_use: null`, distinguishable from a genuine tool
  call, rather than crashing the execution.
- This is the third real bug in this construct only discoverable through
  an actual live execution, not synth-time validation reinforcing the
  same lesson as ADR-0006 and ADR-0007: JSONata expression correctness
  against Bedrock's real response shape cannot be verified without
  running it for real.

## Falsifiability / Verification
- **State (console):** Step Functions console → a fresh execution's
  `Reason (Bedrock Converse)` state → confirm `Output.tool_use` is either
  a populated object (tool requested) or literal `null` (no tool
  requested) never a state-execution error.
  
- **Behavior (CLI):** `invoke_state_machine.py` against a query the model
  can answer directly (e.g. "what is 12 times (3 plus 4)") completes with
  `SUCCEEDED`, not `FAILED` on `States.QueryEvaluationError`.
