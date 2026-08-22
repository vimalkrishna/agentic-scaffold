import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as _lambda
from aws_cdk import Stack
from constructs import Construct

_HANDLER_CODE = """
import ast
import operator

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        return _OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return _OPERATORS[type(node.op)](_eval(node.operand))
    raise ValueError("Unsupported expression")


def handler(event, context):
    tree = ast.parse(event["expression"], mode="eval")
    return {"result": _eval(tree.body)}
"""

_FUNCTION_NAME = "agentic-scaffold-calculator-tool"


class CalculatorTool(Construct):
    """The one trivial tool for commit 1's ReAct loop."""

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        stack = Stack.of(self)

        # Custom role, scoped to exactly this function's own log group —
        # narrower than the default AWSLambdaBasicExecutionRole managed policy.
        execution_role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:{stack.region}:{stack.account}:"
                    f"log-group:/aws/lambda/{_FUNCTION_NAME}:*"
                ],
            )
        )

        self.function = _lambda.Function(
            self,
            "Function",
            function_name=_FUNCTION_NAME,
            role=execution_role,
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            code=_lambda.Code.from_inline(_HANDLER_CODE),
        )
