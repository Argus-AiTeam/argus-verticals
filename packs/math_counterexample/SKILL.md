---
name: math_counterexample
description: "exact counterexample, refutation, scope-correction, and proof-graph campaigns with claim-ledger, Lean 4, and Jacobian verification"
version: 0.1.2
---

# math_counterexample

exact counterexample, refutation, scope-correction, and proof-graph campaigns with claim-ledger, Lean 4, and Jacobian verification.

## How the work goes

The work progresses through `scope` → `solve` → `review`:

- **Scope:** Freeze the exact mathematical statement, quantifiers, normalizations, and objective mode (`targeted` vs. `exploratory`), and record known primary-source theorems and failed routes.
- **Solve:** Construct explicit witnesses, exact symbolic/rational certificates (using Jacobian or standalone exact verifiers), or formal Lean 4 proofs, and maintain the directed dependency graph in `research/PROOF_GRAPH.json`.
- **Review:** Independently replay every computational certificate, verify primary-source proposition alignment, and check that `research/PROOF_GRAPH.json` has zero unproved blocking nodes on the goal path.

## Run the checks

```sh
python3 '<this folder>/proof_graph_check.py' check --project-root .
python3 '<this folder>/proof_graph_check.py' gap --project-root .
```

## Needs

Python 3.11+; `proof_graph_check.py` uses only the Python standard library. Optional tools used by campaigns include Jacobian (`jacobian` CLI / `jacobian-mcp`) for exact symbolic/LP/SMT/integer-matrix certificates and Lean 4 (`lake` / `lean`) for formal proof verification.

## Role references

- manager: [math-research-manager.md](skills/manager/math-research-manager.md)
- planner: [math-research-planning.md](skills/planner/math-research-planning.md)
- engineer: [math-research-execution.md](skills/engineer/math-research-execution.md)
- reviewer: [math-research-review.md](skills/reviewer/math-research-review.md)

## Supporting files

- [LICENSE](LICENSE)
- [proof_graph.py](proof_graph.py)
- [proof_graph_check.py](proof_graph_check.py)
