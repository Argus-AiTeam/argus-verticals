# ale_last_exam

**Purpose:** Agents' Last Exam long-horizon professional workflow in a real sandbox with hidden-reference, artifact-first GUI+CLI delivery.

Single stage (`execute`). Success is the benchmark's post-run scoring of the produced files, so the stage checklist carries the substantive review against the task's own instruction and output locations; there is no generic shell validator.

- `stages.py`: the one-stage contract and role banners.
- `skills/engineer/ale-last-exam-execution.md`, `skills/reviewer/ale-last-exam-delivery-review.md`.

Extras: none. Tests: covered by `tests/test_contract_conformance.py` and `tests/test_voice_wordlist.py`.
