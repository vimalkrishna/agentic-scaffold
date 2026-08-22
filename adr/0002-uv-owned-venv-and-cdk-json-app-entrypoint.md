# ADR-0002: uv-owned .venv and cdk.json app entrypoint

## Status
Accepted (with a documented future-upgrade procedure added below)

## Context
Two related problems surfaced while scaffolding this repo, both in the same
failure category: a tool silently depending on unrecorded local state instead
of fully owning the concern it's responsible for.

**1. `cdk.json` app entrypoint.**
`cdk init --language python` writes `cdk.json` with:
```json
{ "app": "python3 app.py" }
```
This shells out to whatever `python3` resolves to on the current PATH, at the
exact moment `cdk synth`/`cdk deploy` runs not to any specific,
uv-managed environment. It works today, on this machine, because `python3`
currently happens to resolve correctly. It is not guaranteed to work on a
clean machine, a different shell session, or after `uv` is removed and
reinstalled, because nothing records *which* `python3` it depends on.

**2. `.venv` provenance.**
`cdk init` also creates `.venv` via plain `python3 -m venv` +
`pip install -r requirements.txt`. That venv's `pyvenv.cfg` records whatever
interpreter made it, and has no `uv` metadata at all. Layering `uv init` /
`uv add` on top of a pip-created `.venv` risks two failure modes:
- **Version mismatch** if the pip-created venv's interpreter isn't the
  version `uv init --python <X>` expects, `uv add` may refuse it or silently
  recreate it.
- **Mixed provenance** even if versions match, packages `pip` already
  installed aren't tracked in any `uv.lock`. The result is a venv with some
  packages `uv` can reproduce from its lockfile and some it can't account
  for at all.

Both problems share the same root cause: a venv or entrypoint that *works*
today isn't the same as one that's *fully owned* by the tool responsible for
it, end to end.

## Decision

**Fix 1 — `cdk.json`:**
```json
{ "app": "uv run python app.py" }
```
`uv run` resolves and syncs the correct environment itself, every time,
regardless of prior shell state it is self-contained rather than relying on
unrecorded PATH resolution.

**Fix 2 — `.venv` ownership:**
```bash
rm -rf .venv requirements.txt requirements-dev.txt
uv init --python 3.12 --no-readme
uv add aws-cdk-lib constructs
uv add --dev pytest black flake8 cdk-nag
```
Deleting `.venv` before running `uv init`/`uv add` forces `uv` to create it
from scratch, so every package in it is one `uv` put there and can be
reproduced from `uv.lock`. No package in `.venv` has unaccounted-for
provenance.

## Rejected Alternatives

**1. Keep `"app": "python3 app.py"` since it works locally.**
Rejected. "Works on this machine right now" is exactly the failure mode this
ADR exists to catch. It depends on unrecorded state (whatever `python3`
happens to resolve to) rather than a self-contained, reproducible command.

**2. Reuse the pip-created `.venv` and just layer `uv add` on top.**
Rejected. Even where interpreter versions happen to match, this produces a
venv with mixed provenance some packages traceable to `uv.lock`, some not.
A `.venv` that *works* but isn't fully accounted for by the tool meant to own
it defeats the purpose of using `uv` at all.

## Consequences
- `cdk synth`/`cdk deploy`, run locally or in CI, always resolve the same,
  correct Python environment via `uv run`, with no dependency on ambient
  shell state.
- Every package in `.venv` is tracked in `uv.lock` and reproducible via
  `uv sync` on a fresh clone.
- Any future change to the pinned Python version must go through `uv`
  explicitly (see procedure below), not through ad hoc `pip`/`venv` commands,
  to preserve this ownership guarantee.

---

## Addendum: procedure for a future Python version upgrade (e.g. 3.13 → 3.14)

Logged here in advance, per ADR-0003's note that a project-wide move to
Python 3.14 is anticipated but deliberately deferred. This procedure is the
*local tooling* upgrade only it is independent of any single Lambda's
`runtime=` setting (see ADR-0003), which is changed by hand in CDK code, not
through `uv`.

```bash
uv python list      # confirms 3.14 is available to uv
uv python pin 3.14   # updates .python-version to 3.14
rm -rf .venv         # old .venv was built under 3.13 same "don't mix
                     # provenance" reasoning as this ADR's original decision
uv sync              # recreates .venv fresh under 3.14
```

**What `uv sync` actually does after `rm -rf .venv`, step by step:**
1. Reads `.python-version` (now `3.14`).
2. Checks whether `uv` already has a 3.14 interpreter downloaded, under its
   own managed Python installs; if not, `uv` downloads and installs a
   standalone 3.14 build itself this does **not** depend on any
   system-level `python3.14` being present.
3. Creates a new `.venv`, linked to that uv-managed 3.14 interpreter.
4. Installs every dependency listed in `pyproject.toml`, resolved against
   `uv.lock`, into the fresh `.venv`.

The result is a `.venv` with the same ownership guarantee as the original
fix in this ADR: every package in it came from `uv`, traceable to
`uv.lock`, under an interpreter `uv` itself provisioned not a
system Python, not a leftover from a prior version.

**Verification (falsifiability, same pattern as the rest of this repo):**
- **State (console/filesystem):** `cat .venv/pyvenv.cfg` should show
  `version_info = 3.14.x` and a `home` path pointing at `uv`'s managed
  Python install directory, not a system path.
- **Behavior (CLI):** `make ci` should pass with only the tooling changed
  and `calculator_tool.py` still pinned to `PYTHON_3_13` (Lambda runtime is
  unaffected by this local interpreter change) isolating whether the
  tooling upgrade alone introduces any break, before touching the Lambda's
  runtime separately per ADR-0003.