## Code Documentation & Safety Standards

To ensure long-term codebase velocity and zero regression risks, this repository enforces a **Dual-Layer Documentation Standard**:

1. **Macro Intent (The `adr/` Folder):** Every major architectural choice, framework omission (e.g., choosing native JSONata over LangChain), and governance requirement must be recorded as an Architecture Decision Record (ADR).

2. **Micro Execution (Inline Guardrails):** Code files must contain explicit, read-only boundaries (Docstrings) and edge-case explanations (`#` comments) at the point of execution.

### The Traceability Rule
Whenever code implements an architecture pattern governed by an ADR, the module header **MUST** explicitly list the governing ADR number. 

* **Example:** If editing `app_constructs/react_loop/iam.py`, check the header for `[ADR-0006]` dependencies before altering string array loops. Do not abstract logic to make it "vague"; keep definitions explicit and visually traceable to their cloud targets.
