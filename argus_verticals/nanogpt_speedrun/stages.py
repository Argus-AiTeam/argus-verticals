"""NanoGPT Speedrun vertical — Recursive "First Steps" **Task 2**.

Objective: MINIMIZE the wall-clock TIME to train a NanoGPT (modded-nanogpt
lineage) down to a FIXED FineWeb validation loss of **3.28** on an **8×H100**
node. The score is SECONDS-TO-TARGET — lower is better. This is a TIME race,
NOT a BPB-minimization (that is the ``nanochat`` vertical) and NOT a kernel SOL
score (``kernelbench``).

Reference times to beat (Recursive, measured on Modal 8×H100):

    from an unoptimized start   ~186.5 s
    Recursive's best run         ~77.3 s   (faster than record #83 on the
                                            same hardware; PrimeIntellect
                                            leaderboard timing pending)

Same 4-stage setup→optimize→measure→report structure; the metric and the
reviewer's objective framing are TIME-to-target, not val_bpb.
"""
from __future__ import annotations

from pathlib import Path

from argus.verticals.optimization_base import speedrun_base_contract

# Plugin contract read by Argus (argus/verticals/_registry.py): the API
# version and purpose advertise this vertical to the Manager's menu, the skills
# root is seeded like a built-in's, and parents' skill trees are seeded first.
# The stage/checklist contract itself is argus/core/vertical_contract.py.
ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_PURPOSE = "minimize wall-clock time to reach val_loss<=3.28 on modded-nanogpt (8xH100)"
VERTICAL_SKILLS = Path(__file__).resolve().parent / "skills"
VERTICAL_SKILL_PARENTS: tuple[str, ...] = ("speedrun",)

_BASE = speedrun_base_contract()
STAGE_ORDER = list(_BASE.stage_order)
CHECKLIST_STAGE_ORDER = _BASE.stage_order
CHECKLIST_ITEMS = _BASE.checklist_items

completion_gate = "metric"
MISSION_KIND = "optimize"


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    from .capstone import validate_capstone

    return tuple(validate_capstone(project_root, stage))


def role_banner(_role: str) -> str:
    return (
        "MISSION — NanoGPT Speedrun (Recursive Task 2). This is a WALL-CLOCK TIME\n"
        "race, NOT a bits-per-byte task and NOT a kernel-SOL task. Objective:\n"
        "MINIMIZE the seconds to train NanoGPT down to FineWeb val_loss <= 3.28 on\n"
        "an 8×H100 node. Beat Recursive's ~77.3 s (and record #83). The score is\n"
        "seconds-to-target — keep correctness (must actually reach 3.28) but make\n"
        "it FASTER; do NOT trade away reaching the target for raw speed.\n"
    )


__all__ = [
    "STAGE_ORDER",
    "CHECKLIST_STAGE_ORDER", "CHECKLIST_ITEMS",
    "completion_gate", "role_banner", "stage_completion_issues",
]
