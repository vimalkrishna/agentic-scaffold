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
    """
    A wildcard IAM Resource is acceptable in exactly two documented cases,
    both requiring the exception to be visible in the statement itself,
    not just allow-listed by Sid:
      - AWS Marketplace's Subscribe/Unsubscribe/ViewSubscriptions actions
        are account-level operations with no resource-level ARN to scope
        by at all (ADR-0005) — allow-listed by Sid, since no Condition is
        meaningful for them either.
      - CloudWatch PutMetricData (ADR-0012) has no resource-level ARN
        either, but IS scoped by a Condition (cloudwatch:namespace) — so
        instead of a Sid allow-list, this checks that a Condition is
        actually present, which is the real thing making the wildcard safe.
    Every other wildcard Resource is still held to the no-wildcard standard.
    """
    template = _synth_template()
    resources = template.to_json().get("Resources", {})

    # ADR-0005: no resource-level ARN exists for these actions at all, and
    # no Condition is meaningful for them either — Sid allow-list is the
    # only option.
    allowed_wildcard_sids_no_condition_needed = {"BedrockMarketplaceAutoEnablement"}

    for resource in resources.values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        statements = resource["Properties"]["PolicyDocument"]["Statement"]
        for statement in statements:
            if statement.get("Sid") in allowed_wildcard_sids_no_condition_needed:
                continue
            if statement.get("Resource") == "*":
                # ADR-0012: a wildcard Resource is acceptable here ONLY if
                # it's paired with a Condition that actually scopes it —
                # an unconditional bare wildcard is still a failure.
                assert "Condition" in statement, (
                    "Found a wildcard IAM Resource with no Condition and no "
                    "documented ADR-0005-style exception — every permission "
                    "should be scoped to a specific ARN, or a wildcard must "
                    "be paired with a Condition."
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
