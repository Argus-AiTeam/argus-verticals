# prose

**Purpose:** compose or revise literary essays, memoir, or 抒情/叙事散文/随笔; not verse or plot-driven fiction.

Stages `intake → plan → draft → structure_check → review → revise`. Uses `argus_verticals.literary.shared`.

- `stages.py`: contract and completion checks.
- `structure.py`: thin deterministic structure checks.
- `intake.py`, `artifacts.py`, `sources.yaml`.
- `skills/reviewer/prose-review.md`.

Extras: none. Tests: `tests/test_prose_intake.py`, `tests/test_prose_runtime.py`, `tests/test_prose_structure.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
