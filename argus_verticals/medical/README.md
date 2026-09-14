# medical

**Purpose:** biomedical and pharmaceutical evidence execution: target-disease mechanisms, human genetics, preclinical translation, clinical trials, safety, failed programs, competitive pipelines, and auditable non-diagnostic decision dossiers with independent review; not a generic paper pipeline.

Research-kind mission `scope → retrieve → normalize → analyze → review → deliver` with a `certified` completion gate and versioned deliverables.

- `stages.py`: contract, primary deliverables, completion checks.
- `connectors.py`: public PubMed and ClinicalTrials.gov connectors (network).
- `evidence.py`: normalized, source-addressable evidence records.
- `dossier.py`: deterministic dossier builder (`python -m argus_verticals.medical.dossier`).
- `skills/manager/`, `skills/planner/`, `skills/engineer/`, `skills/reviewer/`.

Extras: none. Tests: `tests/skills/test_medical_vertical.py`, `tests/domains/test_medical_connectors.py`, `tests/domains/test_medical_dossier.py`, `tests/domains/test_medical_evidence.py` (fixtures in `tests/domains/fixtures/`).

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
