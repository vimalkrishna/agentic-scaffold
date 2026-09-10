from aws_cdk import Stack
from constructs import Construct


# Regions in Bedrock's "eu" geographic cross-Region inference profile.
# A request can be routed to any of these, so the IAM policy must grant
# the foundation model in every one of them 8,  not just the deploy region.
_EU_GEOGRAPHY_REGIONS = [
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
]


def eu_foundation_model_arns(scope: Construct, model_id: str) -> list[str]:
    """One explicit ARN per region in the 'eu' inference profile's
    destination set. Verbose, but genuinely scoped, no wildcard needed,
    even though the profile itself spans multiple regions."""
    return [
        f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
        for region in _EU_GEOGRAPHY_REGIONS
    ]


def inference_profile_arn(scope: Construct, profile_id: str) -> str:
    """Scoped ARN for a cross-Region inference profile, e.g.
    'eu.amazon.nova-lite-v1:0'."""
    stack = Stack.of(scope)
    return f"arn:aws:bedrock:{stack.region}:{stack.account}:inference-profile/{profile_id}"
