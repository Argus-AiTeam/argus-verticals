"""Independent analog work with selected methods and explicit model limits."""
import os
import shlex
import sys
from pathlib import Path

from argus.skills.stage_machine import ChecklistItem
from argus.verticals._registry import VerticalPlugin

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    evidence_check_command,
    project_file,
    record,
)

from .evidence import PLAN, validate_model, validate_simulation, validate_specification
from .study import resolve_study
from .validation import validate_current

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("analog_mixed_signal requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "analog_mixed_signal")
VERTICAL_PURPOSE = (
    "analog/mixed-signal circuits: bias, small-signal gain, feedback, op-amps, filters, "
    "noise, device models and data-converter interfaces; executable ngspice operating-point, "
    "DC sweep, AC and transient analysis with parameter corners, margins and numerical refinement, "
    "not RTL verification, RF/EM, PCB layout or foundry sign-off"
)
VERTICAL_SKILLS = Path(__file__).parent / "skills"
VERTICAL_SKILL_PARENTS = ()
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("specification", "model", "simulation", "review")
WORKFLOW_MODE = "staged"
completion_gate = "none"
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "specification": {"purpose": "define analog requirements and limits without simulation claims", "stages": ("specification",)},
    "model": {"purpose": "build or assess circuit/model inputs and their validity", "stages": ("model",)},
    "simulation": {"purpose": "run only the requested op/DC/AC/transient analyses on a circuit", "stages": ("simulation",)},
    "review": {"purpose": "check current simulation evidence and explain its limits", "stages": ("simulation", "review")},
    "full": {"purpose": "requirements, model, requested simulations and a limited conclusion", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {
    "specification": (), "model": (), "simulation": (), "review": ("simulation",),
}
CHECKLIST_ITEMS = {
    "specification": (ChecklistItem("analog.requirements", "Observable analog requirements and exclusions are explicit.", "analog/PLAN.json"),),
    "model": (ChecklistItem("analog.models", "Actual circuit/model inputs have named provenance, validity and limitations.", "analog/PLAN.json models and project-local SPICE files"),),
    "simulation": (ChecklistItem("analog.native-analysis", "Requested native analyses are current; envelope coverage and refinements are valid, with fixed-goal diagnosis/design acceptance.", "analog/results/RESULTS.json, native waveforms and optional ASSESSMENT.json"),),
    "review": (ChecklistItem("analog.conclusion", "The conclusion distinguishes ideal/model-dependent simulation from measured or manufactured behavior.", "analog/REVIEW.md and current simulation evidence"),),
}


def render_role_prompt_fragment(
    *, role: str, operation: str, stage: str, scope: str, project_root: Path | None,
) -> str:
    if stage not in STAGE_ORDER:
        return ""
    contract = Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")
    runtime_root = os.environ.get("ARGUS_SKILL_SESSION_ROOT")
    locations = f"Installed analog provider source: `{Path(__file__).resolve().parent}`.\n"
    if runtime_root:
        locations += f"Argus task runtime root: `{Path(runtime_root).resolve()}`. Keep the inherited ARGUS_SKILL_SESSION_ROOT unchanged.\n"
    else:
        locations += "No Argus task runtime root is configured; standalone operating-envelope checks perform full native replay.\n"
    execution = ""
    if stage in {"simulation", "review"}:
        script = (
            "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
            "load_vertical_contract('analog_mixed_signal'); "
            "from argus_verticals.analog_mixed_signal.run_analysis import run_analysis; "
            "print(run_analysis(Path.cwd()))"
        )
        execution = (
            "\nIf the required simulations have not been performed, run this from the "
            "execution project. It requires analog/PLAN.json and refuses existing results:\n\n"
            f"```bash\n{shlex.quote(sys.executable)} -c {shlex.quote(script)}\n```\n"
        )
    return (
        f"## Analog work: {stage}\nApply only the selected scope and requested analysis kinds. "
        "The examples below define record formats, not extra work to perform.\n\n"
        + locations + "\n" + contract + execution
        + "\nEngineer: create records from actual execution. Reviewer: independently "
        "check circuit assumptions, model validity, numerical tolerances and native results "
        "before approving them. Manager/Planner must preserve the stated acceptance conditions.\n"
        "Run this read-only check from the execution project directory; [] and exit 0 "
        "mean the stage's record checks passed, not that the physical circuit is qualified:\n\n"
        f"```bash\n{evidence_check_command('analog_mixed_signal', stage)}\n```\n"
        "Explain missing inputs/tools or failed bounds explicitly. Never manufacture "
        "waveforms, loosen acceptance to obtain a pass, or forge completion records.\n"
    )


def stage_completion_issues(stage: str, project_root: Path, *, state_root: Path | None = None) -> tuple[str, ...]:
    try:
        robustness = "robustness" in record(project_root, PLAN)
        if robustness and stage in {"specification", "model"}:
            resolve_study(project_root)
        elif robustness and stage in {"simulation", "review"}:
            validate_current(project_root, state_root=state_root)
            if stage == "review":
                project_file(project_root, "analog/REVIEW.md")
        elif stage == "specification":
            validate_specification(project_root)
        elif stage == "model":
            validate_model(project_root)
        elif stage == "simulation":
            validate_simulation(project_root)
        elif stage == "review":
            validate_simulation(project_root)
            project_file(project_root, "analog/REVIEW.md")
        else:
            raise ValueError(f"unknown analog stage: {stage}")
    except (EvidenceError, OSError, UnicodeError) as exc:
        return (str(exc),)
    return ()
