import json
import sys

import boto3

"""trace_execution.py — prints a step-by-step call graph for a
ReactLoop execution, given its execution ARN.
Usage: python trace_execution.py <execution_arn>
"""


def trace(execution_arn: str, region: str = "eu-central-1") -> None:
    client = boto3.client("stepfunctions", region_name=region)
    paginator = client.get_paginator("get_execution_history")

    for page in paginator.paginate(executionArn=execution_arn):
        for event in page["events"]:
            details = event.get("stateEnteredEventDetails")
            if details is None:
                continue
            name = details["name"]
            input_snippet = json.loads(details.get("input", "{}"))
            iteration = input_snippet.get("iteration", "-")
            print(f"[{event['timestamp']:%H:%M:%S}] -> {name}  (iteration={iteration})")


if __name__ == "__main__":
    trace(sys.argv[1])
