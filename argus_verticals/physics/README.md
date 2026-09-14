# physics

**Purpose:** theory, simulation, data analysis, literature, or experiment design for a real physical system with bounded evidence.

Proportional workflow `scope → model → execute → review → manuscript`; the final stage checks the compiled paper. Ships no `skills/` directory.

- `stages.py`: contract, role banners, completion checks.
- `tiers.py`, `downgrade.py`: the S/A/B/C/D innovation tier ladder and the auto-downgrade state machine.
- `context_policy.py`: physics-specific context compaction policy.
- `manuscript.py`: outcome check for the compiled manuscript.

Extras: none. Tests: `tests/skills/test_physics_manuscript_contract.py`, `tests/skills/test_physics_runtime_routing.py`, `tests/skills/test_physics_tiered_workflow.py`.
