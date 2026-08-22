# ADR-0001: Step Functions ReAct as the bare agentic baseline (not Bedrock Agents or Strands)

## Status
Accepted

## Context
`rag-scaffold` established a pattern for this portfolio: build the "bare"
version of a capability first the one where nothing is hidden before
layering on managed abstractions. RAG had one dominant pattern (ingest →
embed → store → retrieve → generate) with swappable backends, so choosing
one vector store gave a clean, singular bare baseline.

Agentic AI does not have that same shape. It has three genuinely different
control-flow paradigms, not three backends of the same pattern:

- **Step Functions ReAct** — the observe/reason/act loop is hand-wired by
  the developer; state machine transitions are explicit and visible.
- **Bedrock Agents** — AWS manages the loop; orchestration is hidden behind
  a managed service.
- **Strands Agents** — a framework's own opinion on agent orchestration, a
  different abstraction layer again.

These are different answers to "who owns the loop", a first-principles
question, not interchangeable storage engines the way RAG's vector store
choice was. A single "bare agentic-scaffold" therefore needs a narrower
scope decision than RAG did: which paradigm should the bare baseline teach
first.

A secondary consideration: RAG is a component *of* an agentic system (a tool
an agent can call), not a peer domain to it. This means the bare agentic
baseline should not include RAG as a callable tool in its first commit, 
that would be domain logic (a specific tool choice), the same category of
thing intentionally excluded from `rag-scaffold`'s own baseline.

## Decision
Build `agentic-scaffold` commit 1 as **Step Functions ReAct only**, stripped
to its essentials:
- A state machine implementing observe → reason → act, hand-wired
- One trivial tool (a calculator Lambda)
- Bedrock Converse for reasoning
- Scoped IAM, no wildcards

No RAG, no multi-model routing, no human-in-the-loop gate, no Bedrock Agents,
no Strands. Those are later, separate, deliberately sequenced commits.

## Rejected Alternatives

**1. Bedrock Agents as the bare baseline.**
Rejected. AWS manages the reasoning loop internally: the exact mechanism
this baseline exists to make visible would be hidden behind a managed
service. Valuable as a *second* orchestrator to compare against, once the
hand-built version exists to compare it to, but not as the starting point.

**2. Strands Agents as the bare baseline.**
Rejected for the same reason as Bedrock Agents, a framework's opinionated
orchestration is a different abstraction layer, not the primitive one. Also
a good later comparison point, not a starting point.

**3. A single scaffold covering all three orchestrators from commit 1.**
Rejected. This would conflate three different architectural decisions
("who owns the loop") into one commit, defeating the falsifiable,
one-decision-per-commit structure the rest of this portfolio relies on.
Each orchestrator becomes its own deliberate, later fork instead.

**4. Including RAG as a callable tool in commit 1.**
Rejected. RAG-as-tool is domain logic, not baseline infrastructure, the
same reasoning that kept domain-specific tool choices out of
`rag-scaffold`'s own bare baseline. It becomes the capstone commit, where
Domain 1 (RAG) and Domain 2 (agentic) compose deliberately, rather than
being folded into the primitive from the start.

## Consequences
- Later commits/projects build on this proven baseline in sequence:
  multi-model routing + human-in-the-loop gate; Bedrock Agent and Strands as
  alternative orchestrators (a deliberate architectural fork, comparing what
  each managed layer hides against this hand-built version); RAG-as-tool as
  the capstone, composing Domain 1 and Domain 2.
- Because this baseline is deliberately minimal, most of its early
  debugging surface is tooling/environment issues (uv, cdk.json, cdk-nag),
  not architectural ones, which is itself consistent with "bare baseline
  first": the scope is small enough that non-architectural problems surface
  and get resolved before real complexity is added.

## Falsifiability / Verification
- **State (console):** Step Functions console shows a state machine with
  explicit Reason/Act/Choice states, no hidden orchestration step.
- **Behavior (CLI):** `aws stepfunctions start-execution` + inspecting the
  execution's state-by-state input/output confirms the loop terminates on
  either the model ending its tool use or `max_iterations`, per the
  observe/reason/act cycle this ADR commits to making visible.