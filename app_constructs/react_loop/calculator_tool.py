"""Calculator Action Tool Execution Block.

Implements the deterministic, pure execution function for math utility actions.
This serves as the underlying target for the Step Functions ReAct execution block.

GOVERNING ARCHITECTURE DECISIONS (ADR):
* [ADR-0001] Step Functions ReAct as bare baseline (Pure functional orchestration)
* [ADR-0007] ToolSpec InputSchema.Json must be an object, not a string (Type safety)
* [ADR-TBD]  Deterministic vs. non-deterministic execution boundary for tool
             safety — this file is the deterministic side of that boundary.
             Not yet written as its own ADR; do not cite ADR-0009 here, which
             is the Bedrock Guardrail decision (topic-policy + content
             filters on Reason) and covers a different boundary entirely.

CRITICAL DESIGN RULES FOR MAINTAINERS:
1. STRICTLY DETERMINISTIC: This file must remain 100% mathematical and rule-based.
   Do not introduce LLM calls, heuristics, or fuzzy parsing models inside this file.
2. RIGOROUS EXCEPTION TRAPPING: Real-world arithmetic faults (e.g., division by zero,
   overflow errors, malformed expressions) must be explicitly caught and transformed
   into structured error strings so the downstream JSONata engine can route faults
   predictably, instead of an unhandled exception producing Lambda's raw stack-trace
   error payload.
3. IMMUTABLE JSON CONSTRUCTS: Arguments received by these execution blocks must mirror
   the strict object structures dictated by our ToolSpec. Do not perform raw unmarshaled
   text manipulation.
"""
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
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def handler(event, context):
    # Rule 2: every real-world arithmetic fault must become a structured
    # error string, never an unhandled exception — an unhandled exception
    # here hands ADR-0008's downstream JSONata ($exists() guard on Reason's
    # tool_use) a shape it was never built to expect, on the Act side
    # instead of the Reason side.
    try:
        expression = event["expression"]
    except KeyError:
        return {"error": "Missing required field: 'expression'"}

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
    except ZeroDivisionError:
        return {"error": f"Division by zero in expression: {expression!r}"}
    except SyntaxError:
        return {"error": f"Malformed expression, could not parse: {expression!r}"}
    except OverflowError:
        return {"error": f"Numeric overflow evaluating expression: {expression!r}"}
    except (ValueError, KeyError, TypeError) as exc:
        return {"error": f"Unsupported or invalid expression {expression!r}: {exc}"}

    return {"result": result}
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
