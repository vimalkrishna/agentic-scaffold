#!/usr/bin/env python3
"""
Starts a real Step Functions execution against the deployed ReactLoop state
machine, polls until it finishes, and prints the result.

This is the "CLI for behavior" half of this project's verification pattern —
the console shows state (does the resource exist, what does it look like);
this script confirms behavior (does the loop actually reason, call the tool,
and return an answer).

Usage:
    uv run python scripts/invoke_state_machine.py \
        --state-machine-arn <arn> \
        "what is 12 * (3 + 4)"
"""

import argparse
import json
import sys
import time

import boto3

POLL_INTERVAL_SECONDS = 2
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}


def start_execution(client, state_machine_arn: str, query: str) -> str:
    response = client.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps({"query": query}),
    )
    return response["executionArn"]


def wait_for_completion(client, execution_arn: str) -> dict:
    while True:
        execution = client.describe_execution(executionArn=execution_arn)
        status = execution["status"]
        if status in TERMINAL_STATUSES:
            return execution
        print(f"  ... status: {status}")
        time.sleep(POLL_INTERVAL_SECONDS)


def print_failure_diagnostics(client, execution_arn: str) -> None:
    """On failure, print which state failed and why — narrowing the
    failure to a specific boundary, the same principle used throughout
    this project's ADRs."""
    history = client.get_execution_history(
        executionArn=execution_arn,
        reverseOrder=True,
        maxResults=20,
    )
    for event in history["events"]:
        event_type = event["type"]
        if event_type.endswith("Failed") or event_type.endswith("TimedOut"):
            print(f"\nFailed at event: {event_type}")
            details_key = next(
                (k for k in event if k.endswith("EventDetails")), None
            )
            if details_key:
                print(json.dumps(event[details_key], indent=2))
            return
    print("\nNo specific failure event found in the last 20 history events.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "query", help="The question to send into the ReAct loop"
    )
    parser.add_argument(
        "--state-machine-arn",
        required=True,
        help="ARN of the deployed ReactLoop state machine (see CDK output)",
    )
    args = parser.parse_args()

    client = boto3.client("stepfunctions")

    print(f"Starting execution with query: {args.query!r}")
    execution_arn = start_execution(client, args.state_machine_arn, args.query)
    print(f"Execution ARN: {execution_arn}")

    execution = wait_for_completion(client, execution_arn)
    status = execution["status"]

    print(f"\nFinal status: {status}")

    if status == "SUCCEEDED":
        output = json.loads(execution["output"])
        print("Output:")
        print(json.dumps(output, indent=2))
        return 0
    else:
        print_failure_diagnostics(client, execution_arn)
        return 1


if __name__ == "__main__":
    sys.exit(main())
