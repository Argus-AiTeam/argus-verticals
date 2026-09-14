# literary/shared

Not a vertical. The helper package the five literary verticals (`fiction_writing`, `classical_poetry`, `modern_poetry`, `prose`, `literary_editor`) share.

- `task_envelope.py` (+ `schemas/task_envelope.schema.json`): the intake contract every literary vertical normalizes a request into.
- `review_contract.py` (+ `schemas/review.schema.json`): the structured finding list a literary reviewer emits and the revise stage consumes.
- `artifact_manifest.py` (+ `schemas/artifact_manifest.schema.json`): version and lineage record of the artifacts a mission produces.
- `source_registry.py`, `provenance.py` (+ `schemas/source_usage.schema.json`): rights-and-provenance catalog and the per-mission source-usage log.

Tests: `tests/test_literary_task_envelope.py`, `tests/test_literary_review_contract.py`, `tests/test_literary_artifact_manifest.py`, `tests/test_literary_source_registry.py`, `tests/test_literary_provenance.py`.
