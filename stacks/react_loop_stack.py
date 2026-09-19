from aws_cdk import Stack
from constructs import Construct
from aws_cdk import CfnOutput

from app_constructs.react_loop.calculator_tool import CalculatorTool
# Added IMPORT
from app_constructs.react_loop.guardrail import ReasonGuardrail
# Adding statemachine import ReactLoop, wire up the ReAct loop state machine
from app_constructs.react_loop.iam import inference_profile_arn
from app_constructs.react_loop.iam import eu_foundation_model_arns
from app_constructs.react_loop.state_machine import ReactLoop

# DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"
# eu-central-1 requires the cross-Region inference profile for Nova Lite —
# direct on-demand invocation by base model ID isn't supported there.
INFERENCE_PROFILE_ID = "eu.amazon.nova-lite-v1:0"
BASE_MODEL_ID = "amazon.nova-lite-v1:0"


class ReactLoopStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.calculator_tool = CalculatorTool(self, "CalculatorTool")

        # Added: the guardrail before ReactLoop needs its ARN
        self.reason_guardrail = ReasonGuardrail(self, "ReasonGuardrail")

        # Initially, this was calling State_machine with just three parameters
        # calculator_fn, model_id_for_invocation, iam_resources_for_invocation)
        self.react_loop = ReactLoop(
            self,
            "ReactLoop",
            calculator_fn=self.calculator_tool.function,
            model_id_for_invocation=inference_profile_arn(self, INFERENCE_PROFILE_ID),
            iam_resources_for_invocation=[
                inference_profile_arn(self, INFERENCE_PROFILE_ID),
                *eu_foundation_model_arns(self, BASE_MODEL_ID),
            ],
            guardrail_arn=self.reason_guardrail.guardrail_arn,
            # guardrail_version left at its "DRAFT" default, not passed
        )
# calculator_fn: Points directly to the Lambda function generated
# by CalculatorTool.
# foundation_model_arn: Resolves the ARN for the Amazon Bedrock
# model (amazon.nova-lite-v1:0), granting necessary IAM permissions
# for model invocation.
# CfnOutput: Creates an explicit CloudFormation Output (StateMachineArn).
# Upon deployment via cdk deploy, it displays the ARN of the deployed Step
#  Functions state machine in the terminal.
        CfnOutput(
            self,
            "StateMachineArn",
            value=self.react_loop.state_machine.state_machine_arn,
        )
