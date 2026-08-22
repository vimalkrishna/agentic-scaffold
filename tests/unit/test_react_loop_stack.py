import aws_cdk as cdk
from aws_cdk.assertions import Template

from stacks.react_loop_stack import ReactLoopStack


def _synth_template() -> Template:
    app = cdk.App()
    stack = ReactLoopStack(app, "TestReactLoopStack")
    return Template.from_stack(stack)


# this will test the calculator_tool.py
def test_calculator_lambda_created():
    template = _synth_template()
    template.resource_count_is("AWS::Lambda::Function", 1)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Runtime": "python3.13", "Handler": "index.handler"},
    )


def test_no_wildcard_iam_resources():
    template = _synth_template()
    resources = template.to_json().get("Resources", {})
    for resource in resources.values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        statements = resource["Properties"]["PolicyDocument"]["Statement"]
        for statement in statements:
            assert statement.get("Resource") != "*", (
                "Found a wildcard IAM Resource — every permission should "
                "be scoped to a specific ARN, not '*'."
            )


# def test_state_machine_created():
#     template = _synth_template()
#     template.resource_count_is("AWS::StepFunctions::StateMachine", 1)


# def test_state_machine_uses_jsonata():
#     template = _synth_template()
#     template.has_resource_properties(
#         "AWS::StepFunctions::StateMachine",
#         {"QueryLanguage": "JSONATA"},
#     )