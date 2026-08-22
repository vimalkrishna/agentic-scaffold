from aws_cdk import Stack
from constructs import Construct


def foundation_model_arn(scope: Construct, model_id: str) -> str:
    """Scoped Bedrock foundation-model ARN — never a wildcard, same
    principle used for the IAM role work in calculator_tool.py."""
    stack = Stack.of(scope)
    return f"arn:aws:bedrock:{stack.region}::foundation-model/{model_id}"
