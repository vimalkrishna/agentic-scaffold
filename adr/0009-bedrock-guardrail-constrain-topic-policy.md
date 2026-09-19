# ADR-0009: Bedrock Guardrail on Reason — Topic and Content Policy (Basic Tier, Single-Region)

**Status:** Accepted, verified via live execution

**Date:** 16.09.2026 (verified; originally proposed 2026-09-11)

---

## Context

The ReactLoop baseline (deployed and verified per ADR-0005–0008) invokes Nova Lite via `CallAwsService` on the Reason step, with no content or scope safeguards on what the model receives or returns. As the first Well-Architected cross-cutting commit (Domain 3 AI Safety, Security, Governance), this ADR introduces a Bedrock Guardrail to constrain Reason to arithmetic-relevant queries and to filter harmful content, with IAM scoped to permit only that guardrail's use.

Two independent policy dimensions are in scope for this commit:
- **Topic policy** the agent's mission is arithmetic calculation; general-knowledge queries are off-mission and should be denied rather than answered.
- **Content policy** standard harmful-content filtering (HATE, INSULTS), included to exercise both policy types in one guardrail resource rather than deferring content filtering to a later commit.

Guardrails support an optional `crossRegionConfig` (a system-defined "guardrail profile," e.g. `eu.guardrail.v1:0`) that distributes guardrail evaluation across a Region set this is a separate cross-region mechanism from the Nova Lite inference profile in ADR-0006, not an automatic consequence of it. Standard-tier guardrail capabilities (e.g. prompt-attack detection) require `crossRegionConfig`; Basic-tier content and topic filters do not.

## Decision

Deployed a single `CfnGuardrail` resource, **Basic tier, `eu-central-1` only, no `crossRegionConfig`**:

- **Topic policy**: one DENY-type topic, `GeneralKnowledgeQuestions`, defined as factual/trivia/explanatory requests unrelated to arithmetic calculation, with three example phrases.
- **Content policy**: HATE and INSULTS filters, HIGH strength on both input and output.
- **Distinct `blockedInputMessaging` / `blockedOutputsMessaging`** strings, so verification can distinguish which policy fired from the response alone.

Wired into Reason's existing `CallAwsService` Converse call via a `GuardrailConfig` parameter:

```python
"GuardrailConfig": {
    "GuardrailIdentifier": guardrail_arn,
    "GuardrailVersion": guardrail_version,
    "Trace": "enabled",
}
```

Granted the state machine's IAM role `bedrock:ApplyGuardrail`, scoped to the single guardrail ARN in `eu-central-1` no wildcard, no multi-region resource list.

Used `GuardrailVersion: "DRAFT"` rather than creating a numbered version via `create_guardrail_version`. DRAFT tracks the guardrail's current CDK-deployed configuration directly; promoting to a numbered version introduces a second thing that can drift out of sync during a fast synth/deploy/destroy cycle, and versioning discipline is not yet needed while the policy content itself is still being falsified.

Passed the guardrail's full ARN (not the bare ID) as the constructor parameter into `ReactLoop`, so the same string serves both `GuardrailIdentifier` and the IAM `Resource` without needing to reconstruct an ARN by hand. `ReasonGuardrail` exposes `self.guardrail_arn` for this purpose, following `ReactLoop`'s existing convention of taking primitive strings from sibling constructs rather than construct objects matching `model_id_for_invocation` / `iam_resources_for_invocation`.

## Rejected Alternatives

**Standard tier + `eu` guardrail profile (cross-region guardrail evaluation).** Rejected for this commit. Not functionally required Basic tier fully supports topic and content filters, the only two policy types in scope. Adopting Standard tier now would reintroduce the ADR-0006 multi-region IAM pattern purely as practice, not because the application needs it.

**Content filtering only (skip topic policy).** Rejected. A calculator ReAct agent is unlikely to receive hate-speech prompts in practice content filtering alone would exercise a generic Bedrock feature without testing anything specific to this application's scope. Topic policy is the falsifiable claim that actually matters for an agentic tool-use system.

**Guardrail attached to a separate Finalize invocation (input vs. output split).** Not applicable confirmed live that Finalize is a `sfn.Pass` state with no separate Bedrock call. Reason's single Converse call is the only attachment point.

**Numbered guardrail version instead of DRAFT.** Rejected for now deferred until the policy content itself is no longer expected to change.

## Consequences

- IAM footprint stayed single-region and simple no `allowed_wildcard_sids` exception needed (unlike ADR-0005's Marketplace case).
- DRAFT version means any future policy edit takes effect immediately on next deploy convenient now, needs revisiting before anything resembling production use.
- Implementing and verifying this commit surfaced two issues significant enough to document on their own, see **ADR-0010** for the `GuardrailConfig.Trace` casing bug and the console-edit/code-drift process lesson.

## Verification (Falsifiability layer-isolated) RESULTS

**Console (state):** Confirmed guardrail resource exists in `eu-central-1`, Basic tier, DRAFT version, topic policy shows the one DENY topic, content policy shows HATE + INSULTS at HIGH/HIGH, no `crossRegionConfig` present.

**CLI via `start-execution` + `trace_execution.py` (behavior) topic policy claim:**
Query `"what is the capital of France?"` against the deployed (corrected `Trace: "enabled"`) state machine:
- Trace: `Initialize → Reason (Bedrock Converse) → Continue Loop? → Finalize` no `Act`, confirming the block prevented any tool-use path.
- Reason's output: `"stop_reason": "guardrail_intervened"` a distinct third value, neither `tool_use` nor `end_turn`.
- Finalize's `answer`: `"BLOCKED_BY_TOPIC_POLICY: This request was outside the calculator agent's permitted scope."` the exact configured `blockedInputMessaging` string, confirming the topic policy specifically (not content policy) fired.
- **Claim falsified successfully held.**

**CLI (behavior) arithmetic regression claim:**
Query `"what is 12 times (3 plus 4)"` against the same deployment:
- Trace: `Initialize → Reason(iter 0) → Continue Loop? → Act (Calculator) → Reason(iter 1) → Continue Loop? → Finalize` full loop with one tool call, guardrail attached throughout.
- `"status": "SUCCEEDED"`, final answer contains `84`.
- Noted, not yet explained: the answer text included `<thinking>`/`<response>` tags this run, versus plain `84` on the original baseline run logged as an open observation for Domain 5 (output-quality) work, not resolved here; not a guardrail regression, since the numeric answer was correct and unblocked.
- **Claim falsified successfully held.**

**IAM boundary (behavior):**
Temporarily removed the `AllowApplyGuardrail` policy statement, redeployed, reran the identical off-topic query:
- `"status": "FAILED"`, `"error": "BedrockRuntime.AccessDeniedException"`.
- `"cause"` named the exact assumed role, the exact action (`bedrock:ApplyGuardrail`), and the exact guardrail ARN, 403 status a categorically different failure mode than `guardrail_intervened`.
- Statement restored, redeployed, off-topic query rerun once more confirmed back to `guardrail_intervened`, not `AccessDeniedException`.
- **Claim falsified successfully held.** IAM is confirmed to be the actual gate on guardrail use, not merely a formality.

**Cost discipline:** deployed, ran all three verification passes plus the restore-and-reconfirm redeploy, then destroyed. No stack left running between checks.