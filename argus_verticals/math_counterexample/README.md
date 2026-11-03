# `math_counterexample` — Argus Counterexample & Proof-Graph Math Vertical

This vertical (`argus_verticals.math_counterexample`, manifest [`vertical.json`](vertical.json)) packages the exact `math` vertical workflow, claim ledger (`math_state.py`), directed proof-dependency graph (`proof_graph.py` / `proof_graph_check.py`), primary-source citation verifier (`citation_check.py`), Lean 4 formal-artifact verifier (`lean_evidence.py`), and role skill prompts used in the Argus Live Counterexample Lab campaigns.

## Stages (`scope` → `solve` → `review`)

1. **`scope`** (`explore` verification profile): fix the exact problem statement, quantifiers, normalizations, and `math_objective_mode` (`targeted` vs. `exploratory`), and record known literature status and imported assumptions in `research/MATH_STATE.json`.
2. **`solve`** (`develop` verification profile): construct explicit counterexamples, exact computational/algebraic certificates (via Jacobian or deterministic verifiers), natural-language proofs, or Lean 4 formalizations, maintaining `research/PROOF_GRAPH.json`.
3. **`review`** (`certify` verification profile): independent Reviewer verification of statement fidelity, witness/argument correctness, zero proof-graph gap (`proof_graph_check gap`), and confirmed primary-source citation attributions (`citation_check`).

## CLI Checkers

```bash
python -m argus_verticals.math_counterexample.math_state check --project-root .
python -m argus_verticals.math_counterexample.proof_graph_check check --project-root .
python -m argus_verticals.math_counterexample.proof_graph_check gap --project-root .
python -m argus_verticals.math_counterexample.citation_check status --project-root .
```
