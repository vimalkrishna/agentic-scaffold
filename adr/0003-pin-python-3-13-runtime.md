# ADR-0003: Pin CalculatorTool's Lambda to Python 3.13, not 3.14

## Status
Accepted

## Context
`aws-cdk-lib` (pinned `>=2.265.0`) exposes `Runtime.PYTHON_3_14` as a valid
Lambda runtime. AWS Lambda has supported Python 3.14 as a managed runtime
since November 2025, so this is a real, deployable option, not a
CDK-ahead-of-AWS mismatch.

For this project's baseline commit, the goal is to first build and validate
`CalculatorTool` and the surrounding ReAct loop against Python 3.13 — the
previous LTS runtime, and the version this project's own tooling
(`.python-version`, `.venv`) was originally pinned to — before deliberately
moving the whole project to 3.14 as a separate, later, observable step
(procedure documented in ADR-0002's addendum).

## Decision
```python
runtime=_lambda.Runtime.PYTHON_3_13,
```

## Rejected Alternatives

**1. Use `PYTHON_3_14` immediately, since it's available.**
Rejected. The point of this baseline commit is to observe this construct's
behavior on the *previous* LTS runtime first, as a deliberate comparison
point, before moving to 3.14. Adopting the newest available runtime
immediately would skip that comparison entirely.

**2. Downgrade `aws-cdk-lib` so `PYTHON_3_14` isn't exposed as an option.**
Rejected. Regressing an otherwise-wanted dependency version to avoid a
choice isn't a substitute for making the choice deliberately.

## Consequences
- `CalculatorTool`'s Lambda runs on Python 3.13 until a future, explicit
  ADR records the move to 3.14 project-wide.
- This decision was originally paired with a cdk-nag acknowledgment for the
  `AwsSolutions-L1` "not latest runtime" finding. cdk-nag was subsequently
  removed from this project entirely, for reasons unrelated to this specific
  decision (see ADR-0004). The runtime choice itself stands independently
  of that removal.

## Falsifiability / Verification
- **State (console):** Lambda console shows runtime `Python 3.13` for
  `agentic-scaffold-calculator-tool`.
- **Behavior (CLI):** `grep -n "PYTHON_3" app_constructs/react_loop/calculator_tool.py`
  shows `PYTHON_3_13` literally.