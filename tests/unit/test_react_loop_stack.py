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


def test_state_machine_created():
    template = _synth_template()
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)


def test_state_machine_uses_jsonata():
    template = _synth_template()
    resources = template.to_json()["Resources"]
    state_machines = [
        r
        for r in resources.values()
        if r["Type"] == "AWS::StepFunctions::StateMachine"
    ]
    assert len(state_machines) == 1

    definition_string = state_machines[0]["Properties"]["DefinitionString"]
    # DefinitionString is an Fn::Join of literal text + dynamic references
    # (e.g. the Lambda's ARN). Concatenate just the literal string parts to
    # search the underlying ASL JSON as plain text.
    parts = definition_string["Fn::Join"][1]
    literal_text = "".join(p for p in parts if isinstance(p, str))

    assert '"QueryLanguage":"JSONata"' in literal_text.replace(" ", "")

