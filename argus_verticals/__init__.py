"""Community-maintained Argus verticals (domain packs).

Each subpackage is one Argus vertical: a ``stages.py`` module that implements
the framework's ``VerticalContract`` plus the Skill markdown, schemas, and
helpers that vertical needs. Argus discovers them through the
``argus_skill.verticals`` entry-point group declared in ``pyproject.toml`` and
treats them exactly like its built-in verticals.

Verticals in this package:

- ``ale_last_exam``: Agents' Last Exam long-horizon professional workflows.
- ``chip_design``: end-to-end digital ASIC/accelerator design through sign-off.
- ``classical_poetry``: classical Chinese verse with reproducible prosody checks.
- ``digital_circuit``: RTL, testbenches, formal verification, synthesis, timing.
- ``digital_circuit.benchmark`` (``digital_circuit_benchmark``): single-stage
  fixed-harness RTL benchmark attempts.
- ``fiction_writing``: original narrative prose with a structured story state.
- ``kernelbench``: correctness-checked SOL score / speedup on KernelBench.
- ``literary_editor``: rewrite, expand, polish, proofread, or critique a text.
- ``materials``: materials science and processing across scales.
- ``medical``: biomedical and pharmaceutical evidence dossiers.
- ``modern_poetry``: modern free verse and prose poems.
- ``nanochat``: minimise val_bpb on the nanochat ``train.py``.
- ``nanogpt_speedrun``: minimise wall-clock to a target val_loss on modded-nanogpt.
- ``physics``: theory, simulation, data analysis, or experiment design.
- ``prose``: literary essays, memoir, and lyrical or narrative prose.
- ``quant``: equity factor research producing a reviewer-certified report.
- ``speedrun``: single-metric script/benchmark optimisation under a budget.

``literary/shared`` is not a vertical; it is the helper package the five
literary verticals share (task envelope, review contract, artifact manifest,
source registry, provenance).
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
