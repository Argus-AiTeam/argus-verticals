"""Independent power-electronics knowledge and scoped native converter studies."""
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

from .evidence import validate_simulation
from .model import validate_model, validate_specification
from .study import resolve_study

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("power_electronics requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "power_electronics")
VERTICAL_PURPOSE = (
    "Power electronics: DC-DC converters, power switches and rectifiers, magnetics, "
    "control and protection, losses, filters and layout constraints; native ngspice "
    "Buck/Boost startup, ripple, load-step and finite operating/tolerance studies with margins; not general analog "
    "signal processing, PCB fabrication, RF networks or physical energizing"
)
VERTICAL_SKILLS = Path(__file__).parent / "skills"
VERTICAL_SKILL_PARENTS = ()
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("specification", "model", "simulation", "review")
WORKFLOW_MODE = "staged"
completion_gate = "none"
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "specification": {"purpose": "define power-converter operating conditions and acceptance", "stages": ("specification",)},
    "model": {"purpose": "inspect converter model sources, units and applicability", "stages": ("model",)},
    "simulation": {"purpose": "run only selected native switching-converter studies", "stages": ("simulation",)},
    "review": {"purpose": "independently review current converter waveforms and conclusions", "stages": ("simulation", "review")},
    "full": {"purpose": "requirements, bounded circuit model, selected analyses and conclusion", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {"specification": (), "model": (), "simulation": (), "review": ("simulation",)}
CHECKLIST_ITEMS = {
    "specification": (ChecklistItem("power.requirements", "Operating conditions, observation windows and original numerical limits are explicit.", "power/PLAN.json"),),
    "model": (ChecklistItem("power.models", "Topology, component sources, units and unsupported device behavior are explicit.", "power/PLAN.json and declared models"),),
    "simulation": (ChecklistItem("power.native-results", "Native evidence satisfies the fixed task goal: complete valid diagnosis, or a design meeting all limits and margins.", "power/results/RESULTS.json, native files and any declared operating-envelope assessment"),),
    "review": (ChecklistItem("power.conclusion", "The conclusion distinguishes modeled waveforms from device ratings, real efficiency, hardware safety and physical qualification.", "power/REVIEW.md and current results"),),
}


def render_role_prompt_fragment(*, role: str, operation: str, stage: str, scope: str, project_root: Path | None) -> str:
    if stage not in STAGE_ORDER:
        return ""
    execution = ""
    if stage in ("simulation", "review"):
        script = (
            "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
            "load_vertical_contract('power_electronics'); "
            "from argus_verticals.power_electronics.run_analysis import run_analysis; print(run_analysis(Path.cwd()))"
        )
        execution = (
            "\nExecute selected studies from the project. Existing power/results is never overwritten; "
            "retain failed attempts before an intentional rerun.\n"
            f"```bash\n{shlex.quote(sys.executable)} -c {shlex.quote(script)}\n```\n"
        )
    return (
        f"## Power work: {stage}\nPreserve the original engineering question and requested scope.\n\n"
        + Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")
        + execution
        + "\nEngineer: run actual ngspice. Reviewer: independently examine circuit topology, "
        "units, PWM timing, load change, source signs, stored energy and time-step sensitivity. "
        "Manager/Planner: preserve original limits and do not require unrelated implementation.\n"
        "Use this checker from the execution project. It temporarily re-executes native studies "
        "without modifying the project; [] and exit 0 establish bounded numerical agreement, "
        "not hardware safety, device qualification or measured efficiency.\n"
        "For an operating-envelope diagnosis, task acceptance is not engineering acceptance: "
        "report every failing condition and do not label a failed design as passing. "
        "For a design goal, all declared conditions and required margins must pass.\n"
        f"```bash\n{evidence_check_command('power_electronics', stage)}\n```\n"
        "Do not invent waveforms, relax original bounds, replace switching analysis with averaged "
        "equations, or infer safe hardware operation from an illustrative model.\n"
    )


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    try:
        if stage == "specification":
            plan = validate_specification(project_root)
            if "robustness" in plan:
                resolve_study(project_root)
        elif stage == "model":
            plan = validate_model(project_root)
            if "robustness" in plan:
                resolve_study(project_root)
        elif stage in ("simulation", "review"):
            validate_simulation(project_root)
            if stage == "review":
                project_file(project_root, "power/REVIEW.md")
        else:
            raise ValueError(f"unknown power stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()
