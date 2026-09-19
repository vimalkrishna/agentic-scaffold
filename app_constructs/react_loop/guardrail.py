from aws_cdk import aws_bedrock as bedrock
from constructs import Construct


class ReasonGuardrail(Construct):
    """
    Bedrock Guardrail (Basic Tier, eu-central-1), no crossRegionConfig.
    Constrains Reason step to arithmetic and filters harmful content.
    for the Reason step's Converse call.
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
        # Expose full ARN by key word and not just ID due to *, requirement.
        self.guardrail_arn = self.guardrail.attr_guardrail_arn
        self.guardrail_version = "DRAFT"
