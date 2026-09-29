"""Scoped independent digital verification, not chip implementation."""
from pathlib import Path

from argus.skills.stage_machine import ChecklistItem
from argus.verticals._registry import VerticalPlugin

from .evidence import (
    EvidenceError,
    project_file,
    validate_formal,
    validate_plan,
    validate_simulation,
)

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("digital_circuit_verification requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "digital_circuit", "verification")
VERTICAL_PURPOSE = (
    "independent RTL verification specialty: requirement-to-test matrices, parameter/seed "
    "regressions, protocol scoreboards and nonvacuous formal checks; not RTL implementation, "
    "analog simulation, timing closure or fixed-harness benchmark submission"
)
VERTICAL_SKILL_PARENTS = ("digital_circuit",)
VERTICAL_SKILLS = Path(__file__).parent / "skills"
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("plan", "simulation", "formal", "review")
WORKFLOW_MODE = "staged"
completion_gate = "none"
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "plan": {"purpose": "create the test and property plan only", "stages": ("plan",)},
    "simulation": {"purpose": "execute a parameter/seed matrix on existing RTL", "stages": ("simulation",)},
    "formal": {"purpose": "check properties and reachability under explicit assumptions", "stages": ("formal",)},
    "full": {"purpose": "plan, simulate, check formal properties and review their limits", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {
    "plan": (), "simulation": (), "formal": (), "review": ("plan", "simulation", "formal"),
}
CHECKLIST_ITEMS = {
    "plan": (ChecklistItem("plan.matrix", "Requirements map to observable cases and explicit configurations.", "verification/PLAN.json"),),
    "simulation": (ChecklistItem("simulation.matrix", "Every planned configuration executes independent comparisons for every case.", "verification/RESULTS.json and command output"),),
    "formal": (ChecklistItem("formal.properties", "Properties pass and meaningful covers are reached under explained assumptions.", "verification/FORMAL.json and cover traces"),),
    "review": (ChecklistItem("review.limits", "Results distinguish tested cases, bounded checks and proofs; exclusions remain explicit.", "verification/REVIEW.md"),),
}


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    root = Path(project_root)
    try:
        if stage == "plan":
            validate_plan(root)
        elif stage == "simulation":
            validate_simulation(root)
        elif stage == "formal":
            validate_formal(root)
        elif stage == "review":
            validate_simulation(root)
            validate_formal(root)
            project_file(root, "verification/REVIEW.md")
        else:
            raise ValueError(f"unknown verification stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()
