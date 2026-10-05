"""FPGA scopes keep RTL, implementation and measured board behavior distinct."""
from pathlib import Path

from argus.skills.stage_machine import ChecklistItem
from argus.verticals._registry import VerticalPlugin

from argus_verticals.digital_circuit.verification.evidence import (
    EvidenceError,
    evidence_check_command,
    project_file,
    verification_evidence_contract,
)
from argus_verticals.hardware.shared.review import verification_review_contract

from .evidence import (
    validate_bringup,
    validate_implementation,
    validate_target,
    validate_verification,
)

if "routing_path" not in VerticalPlugin.__dataclass_fields__:
    raise RuntimeError("fpga_design requires Argus vertical routing paths")

ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "fpga_design")
VERTICAL_PURPOSE = (
    "FPGA board projects, resource inference, pin/clock constraints and bring-up; "
    "executable single-clock iCE40 implementation and hardware measurements, scoped RTL "
    "verification or full board delivery; not ASIC physical design or GPU kernels"
)
VERTICAL_SKILL_PARENTS = ("digital_circuit", "digital_circuit_verification")
VERTICAL_SKILLS = Path(__file__).parent / "skills"
STAGE_ORDER = CHECKLIST_STAGE_ORDER = ("requirements", "rtl", "verification", "implementation", "bringup", "delivery")
WORKFLOW_MODE = "staged"
completion_gate = "none"
REQUIRE_INDEPENDENT_REVIEW = True
WORKFLOW_PROFILES = {
    "requirements": {"purpose": "freeze the board, interfaces and acceptance conditions", "stages": ("requirements",)},
    "rtl": {"purpose": "create and verify RTL without implementation or board claims", "stages": ("requirements", "rtl", "verification")},
    "verification": {"purpose": "verify existing RTL for the specified target", "stages": ("verification",)},
    "implementation": {"purpose": "verify and build an existing design without programming a board", "stages": ("verification", "implementation")},
    "bringup": {"purpose": "validate an existing design and its measured board behavior", "stages": ("verification", "implementation", "bringup")},
    "full": {"purpose": "requirements through measured board delivery", "stages": STAGE_ORDER},
}
WORKFLOW_STAGE_REQUIREMENTS = {
    "requirements": (), "rtl": ("requirements", "verification"), "verification": (),
    "implementation": ("verification",), "bringup": ("implementation",),
    "delivery": STAGE_ORDER[:-1],
}
CHECKLIST_ITEMS = {
    "requirements": (ChecklistItem("requirements.target", "Board, part, clock, pins, electrical limits and acceptance conditions are explicit.", "design/FPGA_TARGET.json"),),
    "rtl": (ChecklistItem("rtl.sources", "All declared RTL sources implement the target interfaces.", "RTL sources from design/FPGA_TARGET.json"),),
    "verification": (ChecklistItem("verification.regression", "The target-bound parameter and scenario matrix passes independent comparisons.", "verification/PLAN.json and verification/RESULTS.json"),),
    "implementation": (ChecklistItem("implementation.native-results", "The constrained iCE40 implementation fits resources and reaches its specified clock frequency.", "implementation/BUILD.json and native nextpnr timing.json"),),
    "bringup": (ChecklistItem("bringup.measurements", "The authorized physical device produces the declared observations using the current bitstream.", "bringup/RESULTS.json and measurement output"),),
    "delivery": (ChecklistItem("delivery.reproduction", "The board result is reproducible and its timing, electrical and environmental limits are stated.", "delivery/README.md"),),
}


def render_role_prompt_fragment(
    *, role: str, operation: str, stage: str, scope: str, project_root: Path | None,
) -> str:
    if stage not in STAGE_ORDER:
        return ""
    guidance = (
        f"## FPGA evidence contract: {stage}\n"
        "Apply only the selected scope. Read the provider's canonical record/tool "
        f"contract at {Path(__file__).with_name('README.md')} before execution or "
        "approval. No build or permission string authorizes board programming.\n"
    )
    if stage == "verification":
        guidance += (
            "\n" + verification_evidence_contract()
            + "\nAlso snapshot design/FPGA_TARGET.json and every target source in "
            "RESULTS.json inputs. Target/source changes invalidate the result.\n"
        )
    return (
        guidance
        + "\n" + verification_review_contract()
        + "\nFor Engineer debugging or an execution-capable operator, run this read-only check from the execution "
        "project. [] with exit code 0 accepts record "
        "consistency only; independent review of actual work remains required:\n\n"
        f"```bash\n{evidence_check_command('fpga_design', stage)}\n```\n"
        "Repair reported issues and rerun affected checks; explain what prevents completion, "
        "never weaken acceptance or forge completion records.\n"
    )


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    root = Path(project_root)
    try:
        if stage == "requirements":
            validate_target(root)
        elif stage == "rtl":
            for relative in validate_target(root)["sources"]:
                project_file(root, relative)
        elif stage == "verification":
            validate_verification(root)
        elif stage == "implementation":
            validate_implementation(root)
        elif stage == "bringup":
            validate_bringup(root)
        elif stage == "delivery":
            validate_bringup(root)
            project_file(root, "delivery/README.md")
        else:
            raise ValueError(f"unknown FPGA stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()
