# classical_poetry

**Purpose:** compose or check classical Chinese 近体诗/古体/词 with reproducible 押韵/平仄 prosody and literary review.

Stages `intake → form_plan → compose → prosody_check → review → revise`; `prosody_check` and `review` carry the machine-decidable and reviewer checks. Uses the shared literary contracts in `argus_verticals.literary.shared`.

- `stages.py`: contract and completion checks.
- `prosody.py`: the 平水韵-based prosody engine (`data/pingshui.json`).
- `intake.py`: shared Task Envelope → poetry brief.
- `artifacts.py`: review and artifact vocabularies.
- `sources.yaml`: source registry (rights and provenance).
- `skills/reviewer/prosody-and-conception-review.md`.

Extras: none. Tests: `tests/test_classical_poetry_intake.py`, `tests/test_classical_poetry_prosody.py`, `tests/test_classical_poetry_runtime.py`.
