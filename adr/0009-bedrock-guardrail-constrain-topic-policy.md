# ADR-0009: Bedrock Guardrail on Reason Topic and Content Policy 
## (Basic Tier, Single-Region)

**Status:** Proposed (pending deployment and verification)

**Date:** 2026-09-11

---

## Context

The ReactLoop baseline (deployed and verified per ADR-0005–0008) invokes Nova Lite via `CallAwsService` on the Reason step. There is no content or scope safeguards on what the model receives or returns. As the first Well-Architected cross-cutting commit (Domain 3 AI Safety, Security, Governance), this ADR introduces a Bedrock Guardrail to constrain Reason to arithmetic-relevant queries and to filter harmful content, with IAM scoped to permit only that guardrail's use.

Two independent policy dimensions are in scope for this commit:
- **Topic policy**: the agent's mission is arithmetic calculation; general-knowledge queries are off-mission and should be denied rather than answered.
gqfav 
- **Content policy**: standard harmful-content filtering (HATE, INSULTS), included to exercise both policy types in one guardrail resource rather than deferring content filtering to a later commit.

Guardrails support an optional `crossRegionConfig` (a system-defined "guardrail profile," e.g. `eu.guardrail.v1:0`) that distributes guardrail evaluation across a Region set, this is a separate cross-region mechanism from the Nova Lite inference profile in ADR-0006, not an automatic consequence of it. Standard-tier guardrail capabilities (e.g. prompt-attack detection) require `crossRegionConfig`; Basic-tier content and topic filters do not. This will be implemented later!

## Decision

Deploy a single `CfnGuardrail` resource, **Basic tier, `eu-central-1` only, no `crossRegionConfig`**:

- **Topic policy**: one DENY-type topic, `GeneralKnowledgeQuestions`, defined as factual/trivia/explanatory requests unrelated to arithmetic calculation, with three example phrases.

- **Content policy**: HATE and INSULTS filters, HIGH strength on both input and output.

- **Distinct `blockedInputMessaging` / `blockedOutputsMessaging`** strings, so verification can distinguish which policy fired from the response alone.

Wire the guardrail into Reason's existing `CallAwsService` Converse call via a `GuardrailConfig` parameter (`GuardrailIdentifier`, `GuardrailVersion: "DRAFT"`, `Trace: "ENABLED"`), alongside the existing `ModelId`/`Messages` parameters from ADR-0006/0007.

Grant the state machine's IAM role `bedrock:ApplyGuardrail`, scoped to the single guardrail ARN in `eu-central-1`, no wildcard, no multi-region resource list.

Use `GuardrailVersion: "DRAFT"` rather than creating a numbered version via `create_guardrail_version`. DRAFT tracks the guardrail's current CDK-deployed configuration directly; promoting to a numbered version introduces a second thing (the guardrail resource itself, and the version pointer) that can drift out of sync during a fast synth/deploy/destroy cycle, and versioning discipline is not yet needed while the policy content itself is still being falsified.

## Rejected Alternatives

**Standard tier + `eu` guardrail profile (cross-region guardrail evaluation).** Rejected for this commit. This is not functionally required. Basic tier fully supports topic and content filters, the only two policy types in scope. Adopting Standard tier now would reintroduce the ADR-0006 multi-region IAM pattern (granting `bedrock:ApplyGuardrail` on the guardrail-profile ARN in every EU destination Region) purely as practice, not because the application needs it. It is deliberately deferred, if a later commit needs Standard-tier capability (e.g. prompt-attack detection), that's a new ADR with its own IAM footprint, not folded in here.

**Content filtering only (skip topic policy).** Rejected. A calculator ReAct agent is unlikely to receive hate-speech prompts in practice. The generic Bedrock feature of Content filtering alone without testing anything specific to this application's scope. Topic policy (denying off-mission general-knowledge queries) is the falsifiable claim that actually matters for an agentic tool-use system: does the agent stay within its intended mission when a user pushes it outside that mission.

**Guardrail attached to a separate Finalize invocation (input vs. output split).** Not applicable, confirmed live that Finalize is a `sfn.Pass` state with no separate Bedrock call (Reason's last message passes through directly). This means Reason's single Converse call is the only attachment point, and its guardrail's input/output policy dimensions together constitute the system's full input and output filtering, not two attachment points needing separate configs.

**Numbered guardrail version instead of DRAFT.** Rejected for now. See Decision above deferred until the policy content itself has been verified live and is no longer expected to change.

## Consequences

- IAM footprint for this commit stays single-region and simple no `allowed_wildcard_sids` exception needed (unlike ADR-0005's Marketplace case).
- The guardrail's DRAFT version means any future edit to topic/content policy takes effect immediately on next deploy without a version-promotion step convenient now, but will need revisiting (a real ADR, not a silent change) once this moves toward anything resembling production use, where a stable numbered version and controlled rollout would matter.
- Two regression risks introduced: 
(1) the existing arithmetic query ("what is 12 times (3 plus 4)") must still succeed unblocked the guardrail must not false-positive on legitimate arithmetic phrasing; 
(2) the `CallAwsService` parameter casing (`GuardrailConfig`, PascalCase) is inferred from the Bedrock API shape by analogy to ADR-0006/0007's `ModelId`/`Messages` not yet confirmed against the live `bedrockruntime` service model, so this is a candidate for another "confirmed backwards by live execution" bug in the pattern of ADR-0005–0008.

## Verification (Falsifiability, layer-isolated)

**Console (state):**
- Guardrail resource exists in `eu-central-1`, Basic tier, DRAFT version.
- Topic policy shows one DENY topic (`GeneralKnowledgeQuestions`); content policy shows HATE + INSULTS at HIGH/HIGH.
- No `crossRegionConfig` present.

**CLI via `invoke_state_machine.py` (behavior):**
- Regression: "what is 12 times (3 plus 4)" --> still reaches Finalize with answer 84, **unblocked**.
- Topic policy claim: "what is the capital of France?" --> **blocked**; execution history / guardrail trace confirms `blockedInputMessaging` fired, distinguishing it from a content-policy block.
- (Optional, if time permits this commit) Content policy claim: a deliberately hateful/insulting test input --> blocked with the distinct `blockedOutputsMessaging` or input-side equivalent.

**IAM boundary (behavior):**
- Temporarily remove the `AllowApplyGuardrail` statement from the state machine role, redeploy, and confirm the Converse call fails with a distinct `AccessDenied`-class error not a guardrail block, proving IAM actually gates guardrail use rather than the guardrail being silently bypassable or optional. Restore the statement and redeploy afterward.

**Cost discipline:** deploy, run the three CLI checks above plus the IAM-removal check, then destroy per existing 5–10 minute exceution time. No stack left running between checks.