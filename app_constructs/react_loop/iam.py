"""
IAM ARN Builder Utilities.

This module acts as a READ-ONLY string factory for generating AWS IAM ARNs
required by Bedrock policies.

GOVERNING ARCHITECTURE DECISIONS (ADR):
* [ADR-0006] Bedrock InvokeModel action + EU cross-Region inference profile —
             Nova Lite in eu-central-1 requires the 'eu' inference profile,
             so IAM must be granted across all 8 EU destination Regions, not
             just the deploy region. Both functions below exist to implement
             that requirement without a wildcard resource.

CRITICAL DESIGN RULES FOR MAINTAINERS:
1. NO RESOURCE CREATION: Do not instantiate constructs (`iam.Role`, `iam.Policy`) here.
2. NO POLICY MUTATION: Do not call `.add_to_policy()` or mutate resources inside this file.
3. CONTEXT ONLY: The `scope` argument is strictly used to resolve environment context
   (e.g., `Stack.of(scope).account`) dynamically.
4. DATA OUT: Functions must only return raw strings or lists of strings representing ARNs.
"""
from aws_cdk import Stack
from constructs import Construct


# Regions in Bedrock's "eu" geographic cross-Region inference profile.
# A request can be routed to any of these, so the IAM policy must grant
# the foundation model in every one of them, not just the deploy region.
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
    """Generates explicit foundation model ARNs for all European inference regions.

    Creates one explicit ARN per region in the 'eu' inference profile's destination set.
    This allows tightly scoped IAM policies with no wildcards, even though the underlying
    profile spans multiple geographic regions.

    Args:
        scope: The CDK construct scope (unused here, kept for API consistency).
        model_id: The base model identifier (e.g., 'amazon.nova-lite-v1:0').

    Returns:
        A list of fully qualified Bedrock foundation model ARNs.
        Example item: 'arn:aws:bedrock:eu-west-1::foundation-model/amazon.nova-lite-v1:0'
    """
    # Note: Bedrock foundation models are AWS-managed, so the account ID field
    # in the ARN string remains intentionally blank (::) across all regions.
    return [
        f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
        for region in _EU_GEOGRAPHY_REGIONS
    ]


def inference_profile_arn(scope: Construct, profile_id: str) -> str:
    """Generates a scoped cross-Region inference profile ARN based on deployment context.

    Dynamically resolves the active AWS account and region from the passed CDK scope
    to build the exact target inference profile ARN.

    Args:
        scope: The CDK construct scope used to resolve stack metadata.
        profile_id: The cross-region profile identifier (e.g., 'eu.amazon.nova-lite-v1:0').

    Returns:
        A fully qualified Bedrock inference profile ARN string.
        Example: 'arn:aws:bedrock:eu-west-1:123456789012:inference-profile/eu.amazon.nova-lite-v1:0'
    """
    stack = Stack.of(scope)
    return f"arn:aws:bedrock:{stack.region}:{stack.account}:inference-profile/{profile_id}"
