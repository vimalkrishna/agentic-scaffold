# ADR-0005: AWS Marketplace IAM wildcard exception for Nova Lite auto-enablement

## Status
Accepted

## Context
Amazon Nova Lite is distributed through AWS Marketplace. As of Bedrock's
October 2025 access simplification, there is no longer a manual "Model
access" console step — access to all Bedrock foundation models is enabled
by default with the correct AWS Marketplace permissions, and when a
third-party model is invoked for the first time in an account, Bedrock
automatically initiates the subscription process in the background.

That automatic subscription requires the invoking role to hold three
specific IAM actions: `aws-marketplace:Subscribe`, `Unsubscribe`, and
`ViewSubscriptions`. These are account-level operations, AWS's IAM model
for the `aws-marketplace` service does not support scoping them to a
specific resource ARN. `"*"` is not a convenience shortcut here; it is the
only value AWS permits for these three actions.

This project's stated IAM principle (ADR context throughout this repo, and
enforced by `test_no_wildcard_iam_resources`) is to scope every permission
to a specific ARN, with wildcards used only where AWS itself forces it,
and documented when that happens. This is that documented case.

## Decision
Attach a narrowly-named policy statement (`Sid:
"BedrockMarketplaceAutoEnablement"`) granting exactly the three
Marketplace actions Nova Lite's first-invocation subscription needs, with
`resources=["*"]`, to the Step Functions state machine's execution role:

```python
self.state_machine.role.add_to_policy(
    iam.PolicyStatement(
        sid="BedrockMarketplaceAutoEnablement",
        actions=[
            "aws-marketplace:Subscribe",
            "aws-marketplace:Unsubscribe",
            "aws-marketplace:ViewSubscriptions",
        ],
        resources=["*"],
    )
)
```

`test_no_wildcard_iam_resources` allowlists this exact `Sid` by name, so
this remains the *only* permitted wildcard in the stack, any other
resource that introduces `"*"` still fails the test.

## Rejected Alternatives

**1. Omit these permissions and manually subscribe via the console instead.**
Rejected. This reintroduces a manual, undocumented setup step outside the
CDK stack: exactly the "unrecorded local state" failure category ADR-0002
was written to avoid. A fresh deploy on a clean account should work from
`cdk deploy` alone, not require a human to remember a console click first.

**2. Weaken `test_no_wildcard_iam_resources` generally, rather than
allowlisting this one `Sid`.**
Rejected. A general weakening (e.g. only checking certain resource types,
or dropping the assertion) would silently permit *any* future wildcard to
pass, not just this justified one. Naming the exact `Sid` keeps the test's
original guarantee intact everywhere else.

**3. Scope the resource to the specific model's ARN, matching the pattern
used elsewhere in this project.** Not possible. 
AWS Marketplace's `Subscribe`/`Unsubscribe`/`ViewSubscriptions`
actions are not resource-level actions in AWS's own IAM action reference 
there is no ARN format they accept other than `"*"`. Confirmed against
AWS's own example policy for this exact scenario, which uses `"*"` too.

## Consequences
- The state machine's role can complete Nova Lite's first-invocation
  auto-subscription without any manual console step, on a fresh deploy.
- This is the one place in the stack where `"*"` is permitted, and it's
  enforced to stay that way by name, not by omission.

## Falsifiability / Verification claim
- **State (console):** IAM console → the state machine's role → confirm a
  policy statement with `Sid: BedrockMarketplaceAutoEnablement` exists,
  scoped only to the three named Marketplace actions.

- **Behavior (CLI):** first real execution via
  `invoke_state_machine.py` against a freshly deployed stack (no prior
  Nova Lite invocation in this account) succeeds without a
  `AccessDeniedException` related to Marketplace subscription.