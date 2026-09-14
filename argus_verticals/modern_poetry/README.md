# modern_poetry

**Purpose:** compose or revise modern free verse/prose poems without classical prosody checks; enforce only declared hard constraints.

Stages `intake → plan → compose → form_check → review → revise`. Uses `argus_verticals.literary.shared`.

- `stages.py`: contract and completion checks.
- `form.py`: thin deterministic form checks for declared constraints only.
- `intake.py`, `artifacts.py`, `sources.yaml`.
- `skills/reviewer/modern-verse-review.md`.

Extras: none. Tests: `tests/test_modern_poetry_form.py`, `tests/test_modern_poetry_intake.py`, `tests/test_modern_poetry_runtime.py`.
