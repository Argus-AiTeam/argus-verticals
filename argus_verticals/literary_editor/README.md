# literary_editor

**Purpose:** rewrite, expand, polish, proofread, or critique an existing literary text while preserving edit scope and source facts.

Stages `intake → diagnose → revision_plan → edit → verify`. Uses `argus_verticals.literary.shared`.

- `stages.py`: contract and completion checks.
- `edit_ops.py`: deterministic edit-discipline checks (scope, preserved facts).
- `intake.py`, `artifacts.py`: envelope and artifact adapters; `sources.yaml`.
- `skills/reviewer/edit-review.md`.

Extras: none. Tests: `tests/test_literary_editor_intake.py`, `tests/test_literary_editor_ops.py`, `tests/test_literary_editor_runtime.py`.
