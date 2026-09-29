"""Independent package knowledge and scoped native steady-state thermal evidence."""
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

from .evidence import validate_thermal
from .model import validate_model, validate_specification

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("package_design requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "package_design")
VERTICAL_PURPOSE = (
    "Semiconductor package engineering: die attach, wire bond, flip chip and bumps, "
    "package substrates, interposers, chiplets, thermal paths, mechanical and assembly constraints; "
    "executable Gmsh/CalculiX steady heat conduction through ideal bonded package stacks; "
    "not PCB fabrication, RTL, RF network calculation, general structural FEA or physical qualification"
)
VERTICAL_SKILLS = Path(__file__).parent / "skills"
VERTICAL_SKILL_PARENTS = ()
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("specification", "model", "thermal", "review")
WORKFLOW_MODE = "staged"
completion_gate = "none"
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "specification": {"purpose": "define package interfaces, thermal objectives and physical limits", "stages": ("specification",)},
    "model": {"purpose": "inspect selected package geometry and thermal assumptions", "stages": ("model",)},
    "thermal": {"purpose": "run selected native steady-state package thermal studies", "stages": ("thermal",)},
    "review": {"purpose": "independently review current package thermal evidence", "stages": ("thermal", "review")},
    "full": {"purpose": "requirements, bounded package model, selected studies and conclusion", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {"specification": (), "model": (), "thermal": (), "review": ("thermal",)}
CHECKLIST_ITEMS = {
    "specification": (ChecklistItem("package.requirements", "Interfaces, numerical conditions and unsupported physical claims are explicit.", "package/PLAN.json"),),
    "model": (ChecklistItem("package.models", "Geometry, material sources, SI units and ideal-interface assumptions are explicit.", "package/PLAN.json and declared model files"),),
    "thermal": (ChecklistItem("package.native-results", "Native mesh and temperature/heat fields match current inputs, original bounds and declared refinement comparisons.", "package/results/RESULTS.json and native solver files"),),
    "review": (ChecklistItem("package.conclusion", "The conclusion distinguishes model heat conduction from package reliability, manufacturing and measured behavior.", "package/REVIEW.md and current evidence"),),
}


def render_role_prompt_fragment(*, role: str, operation: str, stage: str, scope: str, project_root: Path | None) -> str:
    if stage not in STAGE_ORDER:
        return ""
    execution = ""
    if stage in ("thermal", "review"):
        script = (
            "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
            "load_vertical_contract('package_design'); "
            "from argus_verticals.package_design.run_analysis import run_analysis; print(run_analysis(Path.cwd()))"
        )
        execution = (
            "\nExecute the selected native studies from the project. Existing package/results is "
            "never overwritten; retain failed attempts before an intentional rerun.\n"
            f"```bash\n{shlex.quote(sys.executable)} -c {shlex.quote(script)}\n```\n"
        )
    return (
        f"## Package work: {stage}\nPreserve the original engineering question and selected scope.\n\n"
        + Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")
        + execution
        + "\nEngineer: execute genuine native tools. Reviewer: independently check units, "
        "interfaces, boundary conditions, conserved heat and mesh sensitivity. Manager/Planner: "
        "preserve original bounds and do not force unrelated stages.\n"
        "Use this checker from the execution project, not session state. It re-executes native "
        "studies temporarily without changing the project; [] and exit 0 establish model "
        "consistency and selected numerical acceptance, not physical package qualification.\n"
        f"```bash\n{evidence_check_command('package_design', stage)}\n```\n"
        "Do not invent native files, loosen limits to pass, infer material properties from "
        "a package label, or claim thermal/stress/reliability coverage beyond the actual model.\n"
    )


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    try:
        if stage == "specification":
            validate_specification(project_root)
        elif stage == "model":
            validate_model(project_root)
        elif stage in ("thermal", "review"):
            validate_thermal(project_root)
            if stage == "review":
                project_file(project_root, "package/REVIEW.md")
        else:
            raise ValueError(f"unknown package stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()
