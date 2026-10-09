"""Independent PCB design knowledge with scoped native KiCad checks and exports."""
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
from argus_verticals.hardware.shared.review import hardware_review_contract

from .design import validate_plan, validate_specification
from .evidence import validate_verification

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("pcb_design requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "pcb_design")
VERTICAL_PURPOSE = (
    "PCB and printed circuit board engineering: schematics, components and footprints, "
    "stackup, placement, routing, return paths and fabrication preparation; "
    "executable KiCad copper-zone refill on copies, ERC/DRC, schematic-board parity, Gerber and Excellon drill outputs; "
    "not RTL, IC layout, RF network calculation, package design, field-solved SI/PI or physical qualification"
)
VERTICAL_SKILLS = Path(__file__).parent / "skills"
VERTICAL_SKILL_PARENTS = ()
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("specification", "design", "verification", "review")
WORKFLOW_MODE = "staged"
completion_gate = "none"
# Round guards (Argus core/round_policy.py; an Argus without per-vertical round
# policies ignores this). Board work is gated by ERC/DRC, schematic-board
# parity and fabrication outputs; a failing native check followed by several
# repair rounds is the normal path, not a stall. The round-count guards are
# off; the Reviewer's explicit FORWARD_PROGRESS=false streak decides (8
# verdicts), with room for a long repair. A Reviewer that stops giving any
# progress judgement is caught after 200 rounds.
ROUND_POLICY = {
    "stall_threshold": 8,
    "no_progress_threshold": 2,
    "soft_round_limit": 0,
    "hard_escalate_rounds": 200,
}
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "specification": {"purpose": "define PCB interfaces, constraints and physical limits", "stages": ("specification",)},
    "design": {"purpose": "inspect a selected schematic or board without forcing fabrication", "stages": ("design",)},
    "verification": {"purpose": "run only requested native checks or fabrication exports", "stages": ("verification",)},
    "review": {"purpose": "independently review selected current native evidence", "stages": ("verification", "review")},
    "full": {"purpose": "requirements, scoped design work, selected checks and a qualified conclusion", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {
    "specification": (), "design": (), "verification": (), "review": ("verification",),
}
CHECKLIST_ITEMS = {
    "specification": (ChecklistItem("pcb.requirements", "Interfaces, constraints, acceptance limits and exclusions are explicit.", "pcb/PLAN.json"),),
    "design": (ChecklistItem("pcb.inputs", "Selected native designs and project-local dependencies are nonempty and explicit.", "pcb/PLAN.json and actual KiCad project"),),
    "verification": (ChecklistItem("pcb.native-results", "Native reports and manufacturing geometry agree with independent execution and original bounds.", "pcb/results/RESULTS.json and native outputs"),),
    "review": (ChecklistItem("pcb.conclusion", "The conclusion separates native checks and file generation from fabrication suitability and physical validation.", "pcb/REVIEW.md and current evidence"),),
}


def render_role_prompt_fragment(*, role: str, operation: str, stage: str, scope: str, project_root: Path | None) -> str:
    if stage not in STAGE_ORDER:
        return ""
    execution = ""
    if stage in ("verification", "review"):
        script = (
            "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
            "load_vertical_contract('pcb_design'); "
            "from argus_verticals.pcb_design.run_analysis import run_analysis; print(run_analysis(Path.cwd()))"
        )
        execution = (
            "\nEngineer: execute only the selected operations from the project directory. Existing pcb/results "
            "is never overwritten; preserve failed attempts before an intentional rerun.\n"
            f"```bash\n{shlex.quote(sys.executable)} -c {shlex.quote(script)}\n```\n"
        )
    return (
        f"## PCB work: {stage}\nPreserve the user's selected scope and original requirements.\n"
        f"Installed PCB provider source: `{Path(__file__).resolve().parent}`.\n\n"
        + Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")
        + execution + "\n" + hardware_review_contract()
        + "\nEngineer: run genuine native tools. Reviewer: independently inspect constraints, "
        "connectivity, manufacturing conventions and current outputs. Manager/Planner: do not "
        "require unrelated stages or relax acceptance to make results pass.\n"
        "For Engineer debugging or an execution-capable operator, use this checker from the "
        "execution project, not session state. It creates a temporary "
        "native replay without changing the project; [] and exit 0 confirm only the selected "
        "recorded checks and exports, not physical board qualification.\n"
        f"```bash\n{evidence_check_command('pcb_design', stage)}\n```\n"
        "Do not invent reports, suppress findings, silently refill or rewrite source boards, "
        "or equate a successful export with fabrication approval.\n"
    )


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    try:
        if stage == "specification":
            validate_specification(project_root)
        elif stage == "design":
            validate_plan(project_root, all_design=True)
        elif stage in ("verification", "review"):
            validate_verification(project_root)
            if stage == "review":
                project_file(project_root, "pcb/REVIEW.md")
        else:
            raise ValueError(f"unknown PCB stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()
