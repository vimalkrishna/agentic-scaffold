# ADR-0006: Explicit `bedrock:InvokeModel` IAM Action and EU Cross-Region Inference Profile for Nova Lite

**Status:** Accepted, verified via live execution

**Date:** 14.09.2026

---

## Context

The baseline ReactLoop (ADR-0001) calls Nova Lite from the Reason step using
`CallAwsService` (`service="bedrockruntime"`, `action="converse"`). Two
assumptions made at design time turned out to be wrong, and both only surfaced
on live execution, after `cdk synth` and the unit tests had passed:

1. **The IAM action CDK derives automatically for this call is wrong.**
2. **Nova Lite cannot be invoked by base model ID in `eu-central-1`.** It must
   be invoked through the `eu` cross-Region inference profile, which changes
   which IAM resources must be granted.

## Decision

**1. Override the auto-derived IAM action.** `CallAwsService` derives the IAM
action from the service and action names. For `bedrockruntime` / `converse`
the derived action does not authorize the call. Set it explicitly:

```python
tasks.CallAwsService.jsonata(
    self,
    "Reason (Bedrock Converse)",
    service="bedrockruntime",
    action="converse",
    iam_action="bedrock:InvokeModel",
    ...
)
```

**2. Invoke via the EU inference profile, not the base model ID.**
`ModelId` is the ARN of the profile `eu.amazon.nova-lite-v1:0`, built by the
`inference_profile_arn()` helper.

**3. Grant IAM on the profile plus every destination Region.** An inference
profile can route a request to any Region in its set, so authorizing only the
deploy Region fails whenever routing lands elsewhere. `iam_resources` contains:

- the inference-profile ARN (account- and Region-scoped), and
- the foundation-model ARN for `amazon.nova-lite-v1:0` in **each of the 8 EU
  destination Regions** (`eu_foundation_model_arns()` in `iam.py`).

These are 8 explicit ARNs, with no wildcard.

## Rejected Alternatives

**Keep the auto-derived IAM action.** Rejected. Confirmed wrong on live
execution: the call was denied even though a Bedrock permission was present.

**Invoke by base model ID (`amazon.nova-lite-v1:0`).** Rejected. Direct
on-demand invocation by base model ID is not supported for Nova Lite in
`eu-central-1`.

**Grant the foundation-model ARN in `eu-central-1` only.** Rejected. The
profile routes across EU Regions, so this works only when routing happens to
stay local, and fails intermittently otherwise. That is worse than failing
every time.

**Wildcard resource (`arn:aws:bedrock:*::foundation-model/*`).** Rejected. It
would violate the project's no-wildcard-IAM test and grant access to every
model in every Region. The only sanctioned wildcard is the Marketplace
exception in ADR-0005, which exists because AWS does not support
resource-scoping those actions.

## Consequences

- The IAM policy is larger (9 resources for the model call) but fully explicit
  and passes the no-wildcard-IAM test.
- The 8-Region list is a maintenance point. If AWS changes the `eu` profile's
  destination set, `eu_foundation_model_arns()` must be updated to match.
- Guardrails later proved to be a separate cross-region mechanism, not covered
  by this profile (see ADR-0009).

## Verification (Falsifiability, layer-isolated)

**Console (state):** the state machine role's policy shows the
`bedrock:InvokeModel` statement with the profile ARN plus 8 foundation-model
ARNs.

**CLI (behavior):**
- Claim: with the explicit `iam_action` and the profile ARN as `ModelId`, the
  Reason step succeeds.
- Evidence: query `"what is 12 times (3 plus 4)"` reached Finalize with answer
  84. [FILL: execution ARN]
- Failure evidence for the rejected paths: [FILL: paste the original
  AccessDenied / ValidationException text from the failed executions]