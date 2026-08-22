from aws_cdk import Stack
from constructs import Construct

from app_constructs.react_loop.calculator_tool import CalculatorTool
# Adding statemachine import ReactLoop, wire up the ReAct loop state machine
from app_constructs.react_loop.iam import foundation_model_arn
from app_constructs.react_loop.state_machine import ReactLoop

DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"


class ReactLoopStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.calculator_tool = CalculatorTool(self, "CalculatorTool")

        self.react_loop = ReactLoop(
            self,
            "ReactLoop",
            calculator_fn=self.calculator_tool.function,
            foundation_model_arn=foundation_model_arn(self, DEFAULT_MODEL_ID),
        )
