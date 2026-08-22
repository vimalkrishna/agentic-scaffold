import aws_cdk as cdk

from stacks.react_loop_stack import ReactLoopStack

app = cdk.App()
ReactLoopStack(app, "ReactLoopStack")

app.synth()
