# ADR-0007: ToolSpec InputSchema.Json must be a JSON object, not a string

## Status
Accepted

## Context
`state_machine.py`'s `_CALCULATOR_TOOL_SPEC` originally serialized
`InputSchema.Json` to a string at synth time, using `json.dumps(...)`:

```python
"InputSchema": {
    "Json": json.dumps({
        "type": "object",
        "properties": {...},
        "required": ["expression"],
    })
}
```

This was based on an AWS re:Post report of a `SCHEMA_VALIDATION_FAILED`
error when passing this field as a nested object instead of a string. 
When this construct was written, likely workaround was applied
preemptively before any real deployment existed to test it against
and flagged explicitly as unverified 
(see the original code comment and ADR-0006's predecessor discussion).

The first real execution against a genuinely live, deployed state machine
(after resolving the IAM and inference-profile issues in ADR-0006)
returned a different, contradicting error:

BedrockRuntime.ValidationException: The format of the value at
toolConfig.tools.0.toolSpec.inputSchema.json is invalid. Provide a json
object for the field and try again.


This is the opposite requirement from the workaround that was applied:
Bedrock's Converse API, invoked via this specific integration path (Step
Functions' `CallAwsService` SDK integration), requires `InputSchema.Json`
to be an actual JSON object not a JSON-encoded string.

## Decision
Revert `InputSchema.Json` to a plain Python dict, letting CDK/Step
Functions serialize it as a native JSON object in the resulting ASL:

```python
"InputSchema": {
    "Json": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "e.g. '12 * (3 + 4)'",
            }
        },
        "required": ["expression"],
    }
}
```

The now-unused `import json` at the top of `state_machine.py` was removed
alongside this change.

## Rejected Alternatives

**1. Keep the stringified version and look for a different way to satisfy
both requirements.**
Rejected. There is no version of this field that is simultaneously a
string and an object the two requirements are directly contradictory,
not two edge cases to reconcile. One of them has to be wrong for this
specific integration path, and the live API's own error message is the
authoritative source for which one.

**2. Trust the AWS re:Post workaround over the live API's error message.**
Rejected. A forum report describes someone else's specific situation 
possibly a different SDK, a different integration path (direct boto3 vs.
Step Functions' `CallAwsService`), or a since-fixed bug. A live
`ValidationException`, from the actual API being called, in the actual
integration path this project uses, is stronger evidence than a
third-party report and should override it when the two disagree.

## Consequences
- This is the second time in this project a forum-sourced or
  documentation-sourced workaround, applied preemptively without a live
  test available, turned out to be wrong once real execution became
  possible (see also ADR-0006's IAM-action derivation issue, discovered
  the same way). The pattern worth internalizing: anything applied
  "defensively," before a real end-to-end test exists, should carry an
  explicit note to re-verify at first real execution and should be
  re-verified, not left in place just because it hasn't caused a problem
  yet.
- No IAM or CDK-synthesis implications this is purely a request-payload
  shape correction.

## Falsifiability / Verification
- **State:** `grep -n "json.dumps" app_constructs/react_loop/state_machine.py`
  returns nothing confirms the stringification is fully removed, not
  just bypassed in one place.
  
- **Behavior (CLI):** a real execution via `invoke_state_machine.py`
  no longer fails with `toolConfig.tools.0.toolSpec.inputSchema.json is
  invalid` the specific, exact error this ADR exists to resolve.