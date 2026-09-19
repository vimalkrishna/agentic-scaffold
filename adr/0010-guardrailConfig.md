# ADR-0010: GuardrailConfig.Trace Casing Bug, and Console-Edit / Code Drift During ADR-0009 Verification

**Status:** Accepted document, two issues found during live verification of ADR-0009

**Date:** 16.09.2026

---

## Context

While deploying and verifying ADR-0009's guardrail, live execution surfaced two distinct issues one a genuine API-contract bug, the other a process gap in how verification was carried out. Neither invalidates ADR-0009's design decisions; both are documented separately here, in the pattern established by ADR-0005–0008, because each is a concrete, reusable lesson independent of the guardrail feature itself.

## Issue-1 `GuardrailConfig.Trace` requires a lowercase value, unlike its sibling keys

**What was assumed:** `GuardrailConfig`'s keys follow Bedrock's Converse API PascalCase convention throughout, consistent with `ModelId` and `Messages` (confirmed correct per ADR-0006/0007). By that pattern, `Trace` was implemented as:

```python
"GuardrailConfig": {
    "GuardrailIdentifier": guardrail_arn,
    "GuardrailVersion": guardrail_version,
    "Trace": "ENABLED",
}
```

**What actually happened:** deploying and invoking with `"Trace": "ENABLED"` produced a `TaskFailed` event at the Reason step the Converse call itself was rejected, not just the guardrail's policy evaluation.

**How it was found:** live execution via the CLI (`start-execution` → `describe-execution` → `TaskFailed`), not caught by `cdk synth`, unit tests, or code review none of which validate the semantic contents of a `Parameters` dict against the live Bedrock API surface.

**Fix, found and verified live in the AWS Console before being ported back to code:**

```python
"GuardrailConfig": {
    "GuardrailIdentifier": guardrail_arn,
    "GuardrailVersion": guardrail_version,
    "Trace": "enabled",
}
```

**Lesson:** unlike `GuardrailIdentifier`/`GuardrailVersion`, `Trace`'s *value* (not just its key) does not follow the surrounding PascalCase convention it takes a lowercase string. This is the same bug *class* as ADR-0006 (wrong auto-derived IAM action) and ADR-0007 (backwards JSON-vs-string assumption): a plausible, pattern-consistent assumption about an AWS API shape that only live execution falsifies. Worth checking casing/value-format per-field, not just per-API, whenever extending `CallAwsService` parameters by analogy to already-verified sibling fields.

## Issue-2 a manual console edit silently desynchronized deployed state from `state_machine.py`

**What happened:** to unblock testing quickly after the `TaskFailed` above, the `Trace` casing fix was applied directly in the Step Functions console's state machine definition not yet ported back to `state_machine.py`. A subsequent `start-execution` run against the console-edited definition succeeded, returning `"stop_reason": "guardrail_intervened"` with the expected blocked message. Shortly after, a separate `start-execution` run issued via the CLI, using what was believed to be an equivalent request instead returned a `TaskFailed`.

**Why this was confusing, and how it was resolved:** the two executions were not, in fact, run against the same state machine definition. The console-run execution used the manually patched (lowercase `Trace`) definition; the CLI-run execution used the CDK-deployed definition, which still had the original, unfixed `"Trace": "ENABLED"` from the last `cdk deploy`. Once the state-machine ARNs involved were checked directly (rather than assumed identical because both were "ReactLoop"), the mismatch was traceable the console edit had never round-tripped back into code and redeployed.

**Resolution:** the fix was ported into `state_machine.py` as the canonical source, then `make deploy` was run to make the CDK-managed definition match what the console edit had proven correct, and the topic-policy test was rerun against that redeployed, code-verified version this is the result recorded as the true ADR-0009 verification outcome, not the earlier console-only run.

**Lesson:** a console edit is a legitimate, fast way to test a hypothesis live, but it is never itself a verified state it's a scratchpad. Two executions that both target "the ReactLoop state machine" are not necessarily targeting the same *definition* of it if one side of that comparison was hand-edited outside of `cdk deploy`. Any console-tested fix must be ported back to source and reverified via a fresh `cdk deploy` before being treated as the ADR's actual evidence matching this project's existing console-for-state / CLI-for-behavior discipline, extended here to cover "state" meaning the deployed *definition* itself, not just resource existence.

## Consequences

- No code or architecture changes beyond what ADR-0009 already describes this ADR is documentation of process and a narrow bug fix, not a new design decision.
- Reinforces a standing practice going forward: after any console-side troubleshooting edit, treat the fix as unverified until it has been ported to source, redeployed via `cdk deploy`, and reverified against the newly deployed ARN never treat a console-run execution result as the recorded verification evidence for an ADR.
- Both issues were found and diagnosed during ADR-0009's live verification logged here in the same spirit as ADR-0005–0008, where the value of the falsifiability framework is in the bugs it surfaces, not just the designs it produces.