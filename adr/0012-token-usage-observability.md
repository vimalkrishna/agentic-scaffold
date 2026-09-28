# ADR-0012: Token-Usage Observability on the Reason State

**Date:** 27.09.2026

## Context
Domain 4 (Operational Efficiency) requires a measured token-usage baseline
before caching is introduced (Skill 4.1.4). Caching's value can only be
falsified against a real before/after token-count comparison, not asserted.

## Decision
Add a `RecordTokenMetrics` state between `Reason` and `Choice`, publishing
`ReasonInputTokens` and `ReasonOutputTokens` as custom CloudWatch metrics in
namespace `AgenticScaffold/ReactLoop`, taken from the `Usage` field of
Bedrock Converse's response on Reason's own output. Invocation *count* is
left to Bedrock's native `AWS/Bedrock` `Invocations` metric, so no custom
code duplicates what CloudWatch already publishes.

## Rejected alternative: `tasks.CallAwsService` for `RecordTokenMetrics`
The first implementation used `CallAwsService` with
`additional_iam_statements` to attach a condition-scoped IAM grant
(`cloudwatch:namespace` condition, since `PutMetricData` has no
resource-level ARN). Rejected after live falsification: `iam_resources` is
mandatory on `CallAwsService` and always auto-generates its own bare,
unconditional statement. `make ci`
(`test_no_bare_wildcard_iam_statements_without_condition`) caught a bare
`Resource: '*'`, no-`Condition` `cloudwatch:PutMetricData` statement sitting
next to the intended condition-scoped one. `additional_iam_statements` adds
a second statement; it does not replace the first, and no documented option
suppresses the auto-generated one.

## Decision (revised): `sfn.CustomState`
`RecordTokenMetrics` is implemented as `sfn.CustomState` with raw ASL
(`Resource: arn:aws:states:::aws-sdk:cloudwatch:putMetricData`), which
generates no IAM of its own. The condition-scoped grant
(`AllowPutTokenMetrics`) is added manually via `role.add_to_policy(...)`
after `self.state_machine` exists, the same pattern as
`BedrockMarketplaceAutoEnablement` (ADR-0005) and `AllowApplyGuardrail`
(ADR-0009). Exactly one IAM statement exists for this action.

## Raw-ASL caveat (learned at first deploy)
`sfn.CustomState` bypasses CDK's type checks, so enum-like values are only
validated by the service at deploy time. The first deploy failed with
`SCHEMA_VALIDATION_FAILED` at `/States/RecordTokenMetrics/QueryLanguage`
because the value was written `"JSONATA"`. The service accepts exactly
`JSONPath` or `JSONata`, case-sensitive. `cdk synth` and `make ci` both
passed with the wrong value, because the existing JSONata test only checks
that the correct string appears somewhere in the definition. Fixed by
writing `"QueryLanguage": "JSONata"`. No new test was added, by decision;
this note is the guard.

## Falsifiable verification claims
1. VERIFIED (`make ci`): `RecordTokenMetrics` exists in the synthesized
   definition, positioned Reason -> RecordTokenMetrics -> "Continue Loop?".

2. VERIFIED (`make ci`): exactly one `cloudwatch:PutMetricData` statement
   exists on the state machine role, `Resource: "*"`, with
   `Condition: {StringEquals: {cloudwatch:namespace:
   "AgenticScaffold/ReactLoop"}}`, and no unconditional duplicate.

3. VERIFIED (live deploy): `cdk synth` succeeding was not sufficient. The
   service rejected the `QueryLanguage` casing until it was corrected (see
   caveat above); after the fix, the stack deployed (CloudFormation green).

4. VERIFIED (live execution): `$states.result.Usage.InputTokens` and
   `OutputTokens` resolve with exactly this PascalCase. The execution
   history shows `usage: {"InputTokens": 432, "OutputTokens": 66, ...}` on
   the first Reason call and `{"InputTokens": 526, "OutputTokens": 59, ...}`
   on the second.

5. VERIFIED (live execution): `"Arguments"` and `"Output"` are accepted as
   the JSONata-mode ASL field names for a `CustomState` Task. The execution
   SUCCEEDED, and `RecordTokenMetrics` returned its input unchanged, so
   `Choice` received the correct shape.

6. VERIFIED (live execution + CloudWatch): one execution of the query
   "What is 12 * (3 + 4)?" made two Reason calls. CloudWatch shows:
   - `ReasonInputTokens`:  SampleCount 2, Sum 958 (432 + 526)
   - `ReasonOutputTokens`: SampleCount 2, Sum 125 (66 + 59)
   Both match the execution history exactly.

7. VERIFIED (live execution): the condition-scoped IAM grant is sufficient
   at runtime. `PutMetricData` succeeded under the
   `cloudwatch:namespace` condition with no other statement present.
   
8. NOT YET VERIFIED: that the native `AWS/Bedrock` `Invocations` metric
   increments once per Reason call. The Decision relies on it for
   invocation count; it has not been checked live.

## Measured baseline (input to the caching ADR)
One execution, query "What is 12 * (3 + 4)?", Nova Lite, guardrail attached:
- Reason invocations: 2
- Input tokens: 958 (432 on call 1, 526 on call 2)
- Output tokens: 125 (66 + 59)
Input tokens rise between calls because the message history, including the
tool result, is sent again on every Reason call. The caching commit should
be compared against these figures using the same query.

## Observations logged for Domain 5 (not resolved here)
The model's `<thinking>...</thinking>` text appears in message content and,
because `Finalize` reads `messages[-1].Content[0].Text`, it also appears in
the final answer. This is the second run showing a different output shape
from the original plain "84" baseline.

## Lesson (meta)
A synth-clean, CI-green state is necessary but not sufficient evidence.
Claims 3 to 7 could only be settled by a live deploy and execution.