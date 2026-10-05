"""Independent RF studies with scoped network models and native numerical comparisons."""
import shlex
import sys
from pathlib import Path

from argus.skills.stage_machine import ChecklistItem
from argus.verticals._registry import VerticalPlugin

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    evidence_check_command,
    project_file,
)

from .evidence import validate_analysis, validate_model, validate_specification

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("rf_design requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "rf_design")
VERTICAL_PURPOSE = (
    "RF and microwave network design: Touchstone/S parameters, impedance matching, "
    "transmission lines, port order and reference impedances, passive cascades, "
    "noise and stability reasoning; executable scikit-rf network analysis and finite component-tolerance/frequency robustness, "
    "not RTL, general SPICE transients, full-wave EM, PCB layout or physical certification"
)
VERTICAL_SKILLS = Path(__file__).parent / "skills"
VERTICAL_SKILL_PARENTS = ()
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("specification", "model", "analysis", "review")
WORKFLOW_MODE = "staged"
completion_gate = "none"
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "specification": {"purpose": "state RF observables, reference planes and limits", "stages": ("specification",)},
    "model": {"purpose": "inspect or construct explicitly limited RF network models", "stages": ("model",)},
    "analysis": {"purpose": "calculate only the requested S-parameter or matching studies", "stages": ("analysis",)},
    "review": {"purpose": "review current RF network evidence and its physical limits", "stages": ("analysis", "review")},
    "full": {"purpose": "requirements, models, selected studies and a qualified conclusion", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {
    "specification": (), "model": (), "analysis": (), "review": ("analysis",),
}
CHECKLIST_ITEMS = {
    "specification": (ChecklistItem("rf.requirements", "Observables, physical assumptions and exclusions are explicit.", "rf/PLAN.json"),),
    "model": (ChecklistItem("rf.models", "Network sources, port conventions, frequency grids and model limits are defined.", "rf/PLAN.json and actual Touchstone inputs"),),
    "analysis": (ChecklistItem("rf.network-results", "Current exported networks agree with the declared calculations and task goal: design meets original limits; diagnosis may validly report failures.", "rf/results/RESULTS.json, retained Touchstone results and selected robustness assessment"),),
    "review": (ChecklistItem("rf.conclusion", "The conclusion distinguishes sampled network calculations from calibration, full-wave and measured hardware claims.", "rf/REVIEW.md and current analysis evidence"),),
}


def render_role_prompt_fragment(
    *, role: str, operation: str, stage: str, scope: str, project_root: Path | None,
) -> str:
    if stage not in STAGE_ORDER:
        return ""
    execution = ""
    if stage in ("analysis", "review"):
        script = (
            "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
            "load_vertical_contract('rf_design'); "
            "from argus_verticals.rf_design.run_analysis import run_analysis; print(run_analysis(Path.cwd()))"
        )
        execution = (
            "\nTo execute the prepared study, run this from the actual project. Existing "
            "rf/results is never overwritten; preserve prior results before an intentional rerun.\n"
            f"```bash\n{shlex.quote(sys.executable)} -c {shlex.quote(script)}\n```\n"
        )
    return (
        f"## RF work: {stage}\nWork only on the selected scope and requested networks.\n\n"
        + Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")
        + execution
        + "\nEngineer: execute the declared calculations. Reviewer: independently check "
        "the reference planes, models, conventions and numerical comparisons. Manager/Planner "
        "must preserve the original acceptance conditions.\n"
        "Use this read-only checker from the execution project, not the session-state directory; "
        "[] and exit 0 mean the declared task goal was accepted, not physical certification. "
        "In robustness diagnosis, inspect ASSESSMENT.json: a valid conclusion may report failed "
        "original limits. Design must pass every original check and required margin.\n"
        f"```bash\n{evidence_check_command('rf_design', stage)}\n```\n"
        "Explain failed bounds or unavailable methods explicitly. Do not invent measured data, "
        "clip bad values, relax requirements to pass, or forge completion records.\n"
    )


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    try:
        if stage == "specification":
            validate_specification(project_root)
        elif stage == "model":
            validate_model(project_root)
        elif stage == "analysis":
            validate_analysis(project_root)
        elif stage == "review":
            validate_analysis(project_root)
            project_file(project_root, "rf/REVIEW.md")
        else:
            raise ValueError(f"unknown RF stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()
