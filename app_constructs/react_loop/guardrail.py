"""Amazon Bedrock Guardrails Context and Execution Hook.

Configures and applies native AWS Bedrock Guardrail configurations to prevent
prompt injections, jailbreaks, PII leakage, and out-of-bounds agent behavior.

GOVERNING ARCHITECTURE DECISIONS (ADR):
* [ADR-0009] Bedrock Guardrail on Reason — Basic tier, eu-central-1, no
             crossRegionConfig; one DENY topic (GeneralKnowledgeQuestions) +
             content filters (HATE/INSULTS HIGH). See rationale and rejected
             alternatives in decisions.md.
* [ADR-TBD]  Deterministic vs. non-deterministic execution boundary for tool
             safety (see calculator_tool.py, the deterministic side of that
             boundary). Not yet written as its own ADR.

CRITICAL DESIGN RULES FOR MAINTAINERS:
1. SYNCHRONOUS, INLINE EVALUATION: This file only defines a CfnGuardrail
   resource at synth time — there is no runtime execution logic here. The
   guardrail is evaluated synchronously, inline, as part of state_machine.py's
   Reason (Bedrock Converse) call. A blocked request surfaces as
   stop_reason == 'guardrail_intervened' in Reason's own output, not as a
   separate async check or a call into this file at runtime.
2. NO CROSS-REGION ROUTING BY DESIGN: ADR-0009 deliberately keeps this
   guardrail Basic tier and single-region (no crossRegionConfig) — unlike the
   Reason state's model invocation, which DOES use the EU cross-Region
   inference profile (ADR-0006). Do not add crossRegionConfig here, and do
   not route this guardrail's identifiers through iam.py's cross-region
   helpers (eu_foundation_model_arns, inference_profile_arn) — those exist
   for the model invocation only and are unrelated to this construct. Adding
   cross-region behavior to the guardrail is a new decision, requiring a new
   ADR, not a silent extension of ADR-0006.
3. STRUCTURED REJECTION VIA CONFIG, NOT EXCEPTIONS: blocked_input_messaging
   and blocked_outputs_messaging below are the structured rejection payload —
   Bedrock returns these as part of a normal (non-exceptional) Converse
   response when a rail trips, which is what lets state_machine.py's JSONata
   route on stop_reason cleanly, with no Python-level exception handling
   needed anywhere in this path.
"""

from aws_cdk import aws_bedrock as bedrock
from constructs import Construct


class ReasonGuardrail(Construct):
    """
    Bedrock Guardrail (Basic Tier, eu-central-1, no crossRegionConfig) that
    constrains the Reason step's Converse call to arithmetic-relevant queries
    and filters harmful content.

    Enforces two independent, falsifiable policies:
      - Topic policy: denies general-knowledge questions (off-mission
        for a calculator agent).
      - Content policy: blocks HATE and INSULTS at HIGH strength.
    See ADR-0009 for rationale and rejected alternatives.
    """

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        # 1. Deploy the CfnGuardrail (Basic Tier, DRAFT version by default)
        self.guardrail = bedrock.CfnGuardrail(
            self,
            "ReasonGuardrail",
            name="react-loop-reason-guardrail",
            description=(
                "Restricts ReactLoop's Reason step to arithmetic-relevant "
                "queries and blocks hate/insult content. ADR-0009."
            ),
            blocked_input_messaging=(
                "BLOCKED_BY_TOPIC_POLICY: This request was outside the "
                "calculator agent's permitted scope."
            ),
            blocked_outputs_messaging=(
                "BLOCKED_BY_CONTENT_POLICY: The model response was "
                "blocked by content safety filters."
            ),
            # 2. Topic Policy: Deny off-mission general-knowledge trivia
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="GeneralKnowledgeQuestions",
                        definition=(
                            "Requests for factual information, trivia, "
                            "history, geography, science explanations, or "
                            "any other general knowledge unrelated to "
                            "performing an arithmetic calculation."
                        ),
                        examples=[
                            "What is the capital of France?",
                            "Explain photosynthesis.",
                            "Who won the World Cup in 2018?",
                        ],
                        type="DENY",
                    )
                ]
            ),
            # 3. Content Policy: HATE and INSULTS at HIGH strength
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="INSULTS",
                        input_strength="HIGH",
                        output_strength="HIGH",
                    ),
                ]
            ),
        )
        # DRAFT is the only version that exists until we explicitly
        # call create_guardrail_version.
        # It is a deliberate choice for this commit, see ADR-0009
        # for why we don't promote to a numbered version yet.
        self.guardrail_id = self.guardrail.attr_guardrail_id
        # Expose the full ARN, not just the ID: state_machine.py passes this
        # same string as both GuardrailIdentifier (Reason's parameters) and
        # the IAM Resource for the AllowApplyGuardrail policy statement, so
        # one value serves both roles without reconstructing the ARN by hand.
        self.guardrail_arn = self.guardrail.attr_guardrail_arn
        self.guardrail_version = "DRAFT"
