# ADR-0004: cdk-nag removed from this project

## Status
Accepted

## Context
`AwsSolutionsChecks` was wired into `app.py` early in this project's
scaffold, intended to provide automated IAM/security-best-practice
validation at synth time (see ADR-0002/0003 history). It initially worked as
expected: a Lambda's non-latest runtime (`AwsSolutions-L1`) and an
AWS-managed IAM policy (`AwsSolutions-IAM4`) were both correctly flagged on
`CalculatorTool` genuine, useful findings.

Acknowledging those findings, however, surfaced a structural incompatibility
between two AWS-maintained tools:

1. cdk-nag v3 replaced its own `NagSuppressions` API with CDK core's generic
   `Validations.of(scope).acknowledge(Acknowledgment(id=..., reason=...))`
   mechanism.
2. CDK core's `Validations.acknowledge()` enforces exactly **one** `::`
   delimiter in the `id` string, splitting `prefix::RuleName`. This is
   documented, deliberate behavior.
3. cdk-nag's own granular findings (`AwsSolutions-IAM4`, `AwsSolutions-IAM5`,
   and others) are reported in the format `RuleName[Detail::Value]`, where
   `Value` is frequently a raw AWS ARN.
4. AWS ARNs routinely contain `::` as ordinary syntax IAM ARNs
   (`arn:aws:iam::<account>:policy/...`), CloudWatch Logs ARNs with
   `<AWS::Region>`/`<AWS::AccountId>` tokens, and others. This is the normal
   shape of these ARNs, not an edge case.
5. Consequently, the exact `"Acknowledge with '...'"` string cdk-nag prints
   as the fix for these findings routinely contains two or three `::`
   sequences and is rejected by `Validations.acknowledge()`'s own
   single-delimiter rule, with a `InvalidValidationId` error, every time.

This was confirmed directly, not assumed: `dir(cdk_nag)` was used to verify
`NagSuppressions` no longer exists in the installed package; the
`Acknowledgment`-object call shape was confirmed against real
`TypeError`s; and the `InvalidValidationId` error was reproduced
independently against both a resource-scoped and an app-scoped
acknowledgment attempt, ruling out "wrong scope" as the cause before
concluding the `id` format itself was the problem.

## Decision
Remove `cdk-nag` and `AwsSolutionsChecks` from this project entirely.

Where cdk-nag's findings pointed at a real improvement, fix the underlying
resource directly instead of acknowledging a finding:
- `CalculatorTool`'s Lambda now uses a custom, narrowly-scoped `iam.Role`
  (exact CloudWatch Logs permissions, scoped to its own log group) instead
  of relying on the default `AWSLambdaBasicExecutionRole` managed policy.
  This resolves the underlying `AwsSolutions-IAM4` concern without needing
  any acknowledgment mechanism at all.

## Rejected Alternatives

**1. Keep working around the `id`-format incompatibility (escaping,
alternate encodings, etc.) to make acknowledgments work.**
Rejected. This is treating a genuine tool defect as a puzzle to solve,
rather than a signal to stop. Time spent reverse-engineering an
undocumented workaround for a cross-tool incompatibility has poor return
for a learning-focused portfolio project, versus fixing the underlying
resource directly (which is both faster and objectively better practice).

**2. Downgrade to an older `cdk-nag` v2 release, to keep `NagSuppressions`.**
Rejected. This trades a real, current problem for a deliberately outdated
dependency, and doesn't change the underlying lesson (this project's
IAM roles should be scoped correctly regardless of whether a linter is
installed to check them).

**3. Suppress findings only at the broadest possible scope (the whole app),
accepting a less precise acknowledgment.**
Rejected before the `id`-format issue was even isolated app-level
acknowledgment attempts hit the identical `InvalidValidationId` error,
confirming the problem was the `id` string itself, not the scope it was
applied at.

## Consequences
- This project has no automated cdk-nag/CloudFormation-Guard-style policy
  validation at synth time going forward. IAM scoping and other
  best-practice concerns rely on manual review and this repo's own unit
  tests (e.g. `test_no_wildcard_iam_resources`) instead.
- The custom IAM role pattern adopted for `CalculatorTool` (explicit role,
  explicit scoped inline policy, no default managed policy) is the template
  for IAM on every construct added going forward in this project not
  because a linter demands it, but because it was already the right call
  once inspected directly.
- If cdk-nag (or an equivalent policy-validation tool) is reconsidered later,
  this ADR's root-cause analysis should be re-checked first: has the `id`
  single-delimiter rule in CDK core, or cdk-nag's granular-finding format,
  changed since this was written.

## Falsifiability / Verification
- **State:** `pyproject.toml` / `uv.lock` show no `cdk-nag` dependency.
  `app.py` contains no `Validations`/`AwsSolutionsChecks` references.
- **Behavior:** `cdk synth` completes with no synthesis errors related to
  policy validation (there is no policy-validation plugin left to raise
  any). `make ci` passes end to end.