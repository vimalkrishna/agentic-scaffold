from aws_cdk import Stack
from constructs import Construct

from app_constructs.react_loop.calculator_tool import CalculatorTool


class ReactLoopStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.calculator_tool = CalculatorTool(self, "CalculatorTool")
