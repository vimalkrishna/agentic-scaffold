"""Step Functions ReAct State Machine Builder.

Defines the native, serverless cloud-native ReAct orchestrator loop using
AWS Step Functions and JSONata.

GOVERNING ARCHITECTURE DECISIONS (ADR):
* [ADR-0001] Step Functions ReAct as bare baseline (No LangChain/CrewAI)
* [ADR-0005] AWS Marketplace IAM wildcard exception (Nova Lite auto-subscription)
* [ADR-0007] ToolSpec InputSchema.Json must be an object, not a string
* [ADR-0008] JSONata expression correctness (Null handling vs. State failure)
* [ADR-0009] Bedrock Guardrail on Reason (topic-policy + content filters)
* [ADR-0010] GuardrailConfig.Trace lowercase; console-edit vs CDK-deployed drift
* [ADR-0012] Token-usage observability (RecordTokenMetrics, CloudWatch namespace)

CRITICAL DESIGN RULES FOR MAINTAINERS:
1. NATIVE JSONata ONLY: State transitions, variables, and history mutations
   must leverage native JSONata syntax. Do not fallback to traditional ASL paths.
   Raw ASL (sfn.CustomState) bypasses CDK's type checks, so enum-like values
   are case-sensitive and only validated by the service at deploy time:
   QueryLanguage must be exactly "JSONata" or "JSONPath" (learned live, ADR-0012).
2. SELF-HEALING TOOL EVALUATION: The 'Act' step must cleanly format either a
   successful result OR a structured tool error into a valid ToolResult schema
   before looping back to 'Reason' — a tool error is shown to the model as
   text, not allowed to silently disappear or fail the state machine execution.
3. IAM CONSTRUCTION: `iam.py` supplies bare resource-ARN strings for grants that
   are simple ARN-scoped permissions (e.g. the Reason state's `iam_action`
   shortcut). A grant with no real resource ARN, or requiring a Condition, is
   added manually via `role.add_to_policy(...)` after `self.state_machine`
   exists (Marketplace, ApplyGuardrail, PutTokenMetrics below) — NOT via
   `CallAwsService`'s `iam_resources`/`additional_iam_statements` kwargs.
   CONFIRMED LIVE (make ci): `CallAwsService`'s `iam_resources` kwarg is
   mandatory and ALWAYS auto-generates its own bare, unconditional statement
   from whatever is passed to it — there is no way to suppress this, even
   when `additional_iam_statements` supplies a better, condition-scoped one
   alongside it. For RecordTokenMetrics (no resource ARN, Condition-scoped),
   this means `sfn.CustomState` (raw ASL, zero auto-generated IAM) is used
   instead of `CallAwsService`, so the manual grant below is the ONLY
   statement produced for that action.
"""
from aws_cdk import Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct

MAX_ITERATIONS = 5

_CALCULATOR_TOOL_SPEC = {
    "ToolSpec": {
        "Name": "calculator",
        "Description": "Evaluates a basic arithmetic expression (+ - * / **) and returns the numeric result.",
        "InputSchema": {
            # Serialized to a string here, at synth time, a documented
            # cdk-nag/Bedrock-integration issue reports SCHEMA_VALIDATION_FAILED
            # when this is passed as a nested object instead.
            "Json": (
                {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "e.g. '12 * (3 + 4)'",
                        }
                    },
                    "required": ["expression"],
                }
            )
        },
    }
}

# ADR-0012: namespace for custom token-usage metrics. Kept as a module
# constant so the Condition below and the PutMetricData call can't drift
# apart from each other.
_TOKEN_METRICS_NAMESPACE = "AgenticScaffold/ReactLoop"


class ReactLoop(Construct):
    """
    Step Functions ReAct loop, built in JSONata (not JSONPath) query language.

    Flow: Initialize -> Reason (Bedrock Converse) -> RecordTokenMetrics -> Choice
          -> [Act (calculator) -> back to Reason] or [Finalize]

    Loop stops on whichever comes first: the model stops requesting the tool
    (stop_reason != 'tool_use'), or max_iterations is reached.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        calculator_fn: _lambda.IFunction,
        model_id_for_invocation: str,
        iam_resources_for_invocation: list[str],
        guardrail_arn: str,
        guardrail_version: str = "DRAFT",
    ) -> None:
        super().__init__(scope, construct_id)

        initialize = sfn.Pass.jsonata(
            self,
            "Initialize",
            outputs={
                "iteration": 0,
                "max_iterations": MAX_ITERATIONS,
                "messages": [
                    {
                        "Role": "user",
                        "Content": [{"Text": "{% $states.input.query %}"}],
                    }
                ],
            },
        )

        reason = tasks.CallAwsService.jsonata(
            self,
            "Reason (Bedrock Converse)",
            service="bedrockruntime",
            action="converse",
            iam_action="bedrock:InvokeModel",
            parameters={
                "ModelId": model_id_for_invocation,
                "Messages": "{% $states.input.messages %}",
                "ToolConfig": {"Tools": [_CALCULATOR_TOOL_SPEC]},
                # ADR-0009: Basic-tier guardrail, single region, no
                # crossRegionConfig. GuardrailIdentifier accepts either
                # a bare ID or a full ARN — we pass the full ARN so the
                # same string also serves the IAM Resource below without
                # needing to reconstruct it by hand.
                "GuardrailConfig": {
                    "GuardrailIdentifier": guardrail_arn,
                    "GuardrailVersion": guardrail_version,
                    "Trace": "enabled",
                },
            },
            iam_resources=iam_resources_for_invocation,
            outputs={
                "iteration": "{% $states.input.iteration + 1 %}",
                "max_iterations": "{% $states.input.max_iterations %}",
                "messages": "{% $append($states.input.messages, [$states.result.Output.Message]) %}",
                "stop_reason": "{% $states.result.StopReason %}",
                "tool_use": (
                    "{% $exists($states.result.Output.Message.Content[ToolUse][0].ToolUse) "
                    "? $states.result.Output.Message.Content[ToolUse][0].ToolUse : null %}"
                ),
                # ADR-0012: preserve token usage for RecordTokenMetrics.
                # UNVERIFIED field casing — per ADR-0010's lesson
                # (GuardrailConfig.Trace lowercase surprise), confirm
                # $states.result.Usage.InputTokens/OutputTokens actually
                # resolves at runtime before trusting this line.
                "usage": "{% $states.result.Usage %}",
            },
        )

        # ADR-0012: token-usage observability, inserted between Reason and
        # Choice. sfn.CustomState issues raw ASL with NO auto-generated IAM
        # at all (unlike CallAwsService — see Rule 3 above), so the manual
        # grant added on self.state_machine.role below is the ONLY IAM
        # statement produced for this action.
        # FIXED LIVE (first deploy): QueryLanguage was "JSONATA" and the
        # service rejected it (SCHEMA_VALIDATION_FAILED) — the accepted values
        # are exactly "JSONPath" or "JSONata", case-sensitive. cdk synth and
        # make ci could not catch this; only the service validates it.
        # STILL UNVERIFIED: that "Arguments"/"Output" behave correctly at
        # execution time. The service raised no schema error for them.
        record_token_metrics = sfn.CustomState(
            self,
            "RecordTokenMetrics",
            state_json={
                "Type": "Task",
                "QueryLanguage": "JSONata",
                "Resource": "arn:aws:states:::aws-sdk:cloudwatch:putMetricData",
                "Arguments": {
                    "Namespace": _TOKEN_METRICS_NAMESPACE,
                    "MetricData": [
                        {
                            "MetricName": "ReasonInputTokens",
                            "Value": "{% $states.input.usage.InputTokens %}",
                            "Unit": "Count",
                        },
                        {
                            "MetricName": "ReasonOutputTokens",
                            "Value": "{% $states.input.usage.OutputTokens %}",
                            "Unit": "Count",
                        },
                    ],
                },
                "Output": "{% $states.input %}",
            },
        )

        act = tasks.LambdaInvoke.jsonata(
            self,
            "Act (Calculator)",
            lambda_function=calculator_fn,
            payload=sfn.TaskInput.from_object(
                {"expression": "{% $states.input.tool_use.Input.expression %}"}
            ),
            outputs={
                "iteration": "{% $states.input.iteration %}",
                "max_iterations": "{% $states.input.max_iterations %}",
                # Self-healing tool evaluation (Rule 2): calculator_tool.py
                # returns either {"result": ...} or {"error": ...} — never an
                # unhandled exception. This surfaces whichever key is present
                # as the ToolResult text, so a tool-side fault is shown to
                # the model as readable text and the loop continues.
                "messages": (
                    "{% $append($states.input.messages, [{"
                    "'Role': 'user', "
                    "'Content': [{'ToolResult': {"
                    "'ToolUseId': $states.input.tool_use.ToolUseId, "
                    "'Content': [{'Text': $string("
                    "$exists($states.result.Payload.result) "
                    "? $states.result.Payload.result "
                    ": $states.result.Payload.error"
                    ")}]"
                    "}}]"
                    "}]) %}"
                ),
            },
        )

        finalize = sfn.Pass.jsonata(
            self,
            "Finalize",
            outputs={"answer": "{% $states.input.messages[-1].Content[0].Text %}"},
        )

        should_continue = sfn.Condition.jsonata(
            "{% $states.input.stop_reason = 'tool_use' and $states.input.iteration < $states.input.max_iterations %}"
        )
        choice = sfn.Choice.jsonata(self, "Continue Loop?").when(should_continue, act).otherwise(finalize)

        act.next(reason)
        # ADR-0012: Reason now flows through RecordTokenMetrics before
        # reaching Choice, instead of straight to Choice.
        definition = initialize.next(reason).next(record_token_metrics).next(choice)

        self.state_machine = sfn.StateMachine(
            self,
            "StateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            query_language=sfn.QueryLanguage.JSONATA,
            timeout=Duration.minutes(5),
        )
        # Nova Lite is distributed via AWS Marketplace. On first invocation
        # in this account, Bedrock auto-initiates a subscription, but only
        # if the calling role has these permissions. AWS Marketplace's
        # Subscribe/Unsubscribe/ViewSubscriptions actions don't support
        # resource-level scoping (account-level operations), so "*" here is
        # the only valid value, not a shortcut. See ADR-0005.
        self.state_machine.role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockMarketplaceAutoEnablement",
                actions=[
                    "aws-marketplace:Subscribe",
                    "aws-marketplace:Unsubscribe",
                    "aws-marketplace:ViewSubscriptions",
                ],
                resources=["*"],
            )
        )

        # ADR-0009: unlike the Marketplace actions above, ApplyGuardrail
        # DOES support resource-level scoping, scoped to the single
        # guardrail ARN, single region (eu-central-1), no wildcard.
        self.state_machine.role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowApplyGuardrail",
                effect=iam.Effect.ALLOW,
                actions=["bedrock:ApplyGuardrail"],
                resources=[guardrail_arn],
            )
        )

        # ADR-0012: CloudWatch PutMetricData has no resource-level ARN, same
        # category as the Marketplace actions above — genuinely scoped only
        # by Condition, not Resource. sfn.CustomState (above) generates no
        # IAM of its own, so this is the ONLY statement for this action.
        self.state_machine.role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowPutTokenMetrics",
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": _TOKEN_METRICS_NAMESPACE
                    }
                },
            )
        )
