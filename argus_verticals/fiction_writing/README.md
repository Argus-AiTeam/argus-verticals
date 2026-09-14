# fiction_writing

**Purpose:** write or continue original fiction narrative prose while preserving characters, world, and timeline; not a literature review or research task.

Stages `intake → plan → draft → state_update → review → revise`, reviewer judgment closes it (`completion_gate = "none"`). Built on the shared literary contracts in `argus_verticals.literary.shared`.

- `stages.py`: contract and completion checks.
- `state.py`, `state_patch_io.py`: the structured `story_state` core, its JSON schemas (`schemas/`), and the safe patch engine.
- `temporal.py`: deterministic timeline/age consistency check.
- `style.py`, `style_lint.py`, `references/voice_cards/`: voice cards and the anti-AI style lint.
- `novelty.py`: anti-copy check; folds 繁/简 when `opencc` is installed (`argus-verticals[zh-fold]`).
- `intake.py`, `revise.py`, `artifacts.py`, `sources.py`, `profiles.py`, `ingest.py`: envelope, review, artifact, source and genre adapters.
- `evaluations/run_evals.py`, `evaluations/calibrate_novelty.py`: live evaluation and calibration harnesses (need a model backend).
- `examples/honglou/`: a valid seed canon used as a live fixture.
- `skills/engineer/`, `skills/reviewer/`.

Extras: `zh-fold` (optional). Tests: `tests/test_fiction_writing*.py`.
