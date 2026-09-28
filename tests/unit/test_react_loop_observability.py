import json
import pytest
from aws_cdk import App
from aws_cdk.assertions import Template, Match

from stacks.react_loop_stack import ReactLoopStack


@pytest.fixture
def template() -> Template:
    app = App()
    stack = ReactLoopStack(app, "TestReactLoopStack")
    return Template.from_stack(stack)


def test_record_token_metrics_state_exists_in_definition(template: Template):
    """
    Falsifies: RecordTokenMetrics is missing, or wired to the wrong states.
    We inspect the raw DefinitionString rather than just checking a resource
    exists, because a state with the wrong Next/Arguments would still create
    *a* Task resource — the state machine JSON is the only place that
    actually proves the wiring.
    """
    resources = template.find_resources("AWS::StepFunctions::StateMachine")
    assert len(resources) == 1

    state_machine = list(resources.values())[0]
    definition_str = state_machine["Properties"]["DefinitionString"]

    if isinstance(definition_str, dict) and "Fn::Join" in definition_str:
        parts = definition_str["Fn::Join"][1]
        literal_parts = [p for p in parts if isinstance(p, str)]
        definition_json = json.loads("".join(literal_parts))
    else:
        definition_json = json.loads(definition_str)

    states = definition_json["States"]

    assert "RecordTokenMetrics" in states, "RecordTokenMetrics state missing from definition"

    # Real state-machine keys are the construct IDs verbatim, not the
    # shorthand names used in prose/comments — confirmed live via the
    # KeyError this test previously raised.
    reason_state = states["Reason (Bedrock Converse)"]
    record_metrics_state = states["RecordTokenMetrics"]

    assert reason_state.get("Next") == "RecordTokenMetrics", (
        "Reason must transition to RecordTokenMetrics before Choice — "
        "if this fails, token metrics are being skipped"
    )

    assert record_metrics_state.get("Next") == "Continue Loop?", (
        "RecordTokenMetrics must transition to the Choice state "
        "('Continue Loop?') — if this fails, the loop is broken "
        "downstream of the metrics call"
    )

    # result passthrough: Choice must not see PutMetricData's own response
    # shape merged into its input.
    assert record_metrics_state.get("Output") is None or "PutMetricData" not in json.dumps(
        record_metrics_state.get("Output", {})
    ), "PutMetricData's response must not leak into downstream state input"


def test_put_metric_data_iam_is_condition_scoped_not_bare_wildcard(template: Template):
    """
    Falsifies: the IAM statement for cloudwatch:PutMetricData is a bare
    Resource: '*' with no Condition. This is looser than
    test_no_bare_wildcard_iam_statements_without_condition below (it only
    proves ONE matching statement exists, not that no bad one exists
    alongside it) — kept as a positive-case check, not the sole guard.
    """
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Action": "cloudwatch:PutMetricData",
                                "Effect": "Allow",
                                "Resource": "*",
                                "Condition": {
                                    "StringEquals": {
                                        "cloudwatch:namespace": "AgenticScaffold/ReactLoop"
                                    }
                                },
                            }
                        )
                    ]
                )
            }
        },
    )


def test_no_bare_wildcard_iam_statements_without_condition(template: Template):
    """
    Repo-wide guard (mirrors your existing make ci check): any IAM
    statement with Resource: '*' must carry a Condition block, UNLESS it's
    a documented ADR-0005-style exception (AWS Marketplace's account-level
    actions have no resource-level ARN to scope by, and no Condition is
    meaningful for them either).
    """
    allowed_wildcard_sids = {"BedrockMarketplaceAutoEnablement"}

    policies = template.find_resources("AWS::IAM::Policy")

    for policy in policies.values():
        statements = policy["Properties"]["PolicyDocument"]["Statement"]
        if not isinstance(statements, list):
            statements = [statements]

        for stmt in statements:
            if stmt.get("Sid") in allowed_wildcard_sids:
                continue
            if stmt.get("Resource") == "*" or stmt.get("Resource") == ["*"]:
                assert "Condition" in stmt, (
                    f"Bare wildcard IAM statement without Condition: {stmt.get('Action')} — "
                    "either scope the resource, add a Condition, or document a new "
                    "ADR-0005-style exception with rejected alternatives"
                )
