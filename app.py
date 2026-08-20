import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks, Validations

from stacks.react_loop_stack import ReactLoopStack

app = cdk.App()
ReactLoopStack(app, "ReactLoopStack")

# Validations.of(...).add_plugins(...) is the current cdk-nag v3 API.
# The older Aspects.of(app).add(AwsSolutionsChecks()) pattern breaks on v3.
Validations.of(app).add_plugins(AwsSolutionsChecks(app))

app.synth()