# ADR-0011: Step Functions ReAct Loop vs. Bedrock AgentCore Runtime

**Date:** 27.09.2026

---

## Context
Amazon Bedrock AgentCore provides a managed agent platform, Runtime/Harness,
Memory, Gateway, Identity, Observability, Policy, Evaluations, that overlaps
substantially with the ReactLoop being built by hand on Step Functions + Lambda
in this repo. It would be reasonable to ask why a custom orchestration layer 
was built when a managed equivalent exists.

## Decision
Continue building ReactLoop on Step Functions (JSONata) + direct Bedrock Converse
calls, rather than migrating to AgentCore Runtime, for the remainder of this
portfolio.

## Rationale
- The portfolio's purpose is to demonstrate competency across the *primitives* 
  AgentCore abstracts: state machine design, guardrail wiring at the
  API level, IAM least-privilege boundaries, token accounting, retrieval tuning.
  Building on AgentCore Runtime directly would hide exactly the mechanics being
  tested for.
- Step Functions' native state visibility (console execution history, per-state
  IAM, JSONata query language) gives layer-isolated falsifiability, each ADR in
  this repo depends on being able to prove *which state* failed and why.
- Cost/complexity is proportional to a single-tool baseline; AgentCore's value
  (session isolation microVMs, cross-framework support, managed multi-agent
  registry) pays off at a scale and multi-agent complexity this project hasn't
  reached yet.

## Rejected Alternative
Migrate ReactLoop to AgentCore Runtime/Harness now stands Rejected: would 
collapse ADR-0006 through ADR-0010's hard-won, falsifiable evidence about Bedrock 
IAM boundaries and guardrail wiring into a managed abstraction, defeating the
portfolio's demonstrative purpose at this stage.

## Forward-looking note (not a decision, for the human-in-the-loop phase)
When the API Gateway + Cognito browser-interface phase begins, AgentCore
Identity and Gateway become directly relevant prior even if not adopted:

- **AgentCore Identity** solves agent-distinct-from-user credential vaulting 
  the same problem a Cognito-fronted agent API will face 
  (should the agent's Bedrock IAM role be end-user-scoped or service-scoped?).

- **AgentCore Gateway** is the managed version of "turn a Lambda into a
  governed, discoverable MCP tool with auth" directly relevant once
  `CalculatorTool` needs to be one of several agent-callable tools exposed
  behind API Gateway.
  
- **AgentCore Memory** is the managed version of the DynamoDB conversation-
  history component implied by Skill 1.6.2, if/when the human-in-the-loop
  phase needs multi-turn session memory.

*"I know AgentCore exists and would use its Identity/Gateway services in a
production build past this phase; I built the primitives by hand here to 
understand what those services are managing."*

## Falsifiable verification claim
None required, this is a design-rationale ADR, not an implementation ADR. 
No infrastructure changes accompany it.