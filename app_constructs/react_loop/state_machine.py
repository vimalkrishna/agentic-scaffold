import json

from aws_cdk import Duration
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
            "Json": json.dumps(
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


class ReactLoop(Construct):
    """
    Step Functions ReAct loop, built in JSONata (not JSONPath) query language.

    Flow: Initialize -> Reason (Bedrock Converse) -> Choice
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
        foundation_model_arn: str,
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
            parameters={
                "ModelId": foundation_model_arn,
                "Messages": "{% $states.input.messages %}",
                "ToolConfig": {"Tools": [_CALCULATOR_TOOL_SPEC]},
            },
            iam_resources=[foundation_model_arn],
            outputs={
                "iteration": "{% $states.input.iteration + 1 %}",
                "max_iterations": "{% $states.input.max_iterations %}",
                "messages": "{% $append($states.input.messages, [$states.result.Output.Message]) %}",
                "stop_reason": "{% $states.result.StopReason %}",
                "tool_use": "{% $states.result.Output.Message.Content[ToolUse][0].ToolUse %}",
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
                "messages": (
                    "{% $append($states.input.messages, [{"
                    "'Role': 'user', "
                    "'Content': [{'ToolResult': {"
                    "'ToolUseId': $states.input.tool_use.ToolUseId, "
                    "'Content': [{'Text': $string($states.result.Payload.result)}]"
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
        definition = initialize.next(reason).next(choice)

        self.state_machine = sfn.StateMachine(
            self,
            "StateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            query_language=sfn.QueryLanguage.JSONATA,
            timeout=Duration.minutes(5),
        )
