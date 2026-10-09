"""Chip and accelerator design vertical, run on checkable evidence.

The vertical spans product/workload definition through RTL, verification,
PPA, prototyping, benchmark comparison, and final sign-off. It supports
synthesizable IP, FPGA prototypes, open-PDK GDS, and tapeout-readiness
missions without pretending those delivery levels are interchangeable.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from argus.core.vertical_contract import VerticalContract
from argus.skills.stage_machine import ChecklistItem

from argus_verticals.hardware.shared.evidence import evidence_check_command
from argus_verticals.hardware.shared.review import verification_review_contract

from .control_report import validate_completion

if not hasattr(VerticalContract, "compose_workflow"):
    raise RuntimeError("chip_design 1.x requires Argus composable workflow support")

# Plugin contract read by Argus (argus/verticals/_registry.py): the API
# version and purpose advertise this vertical to the Manager's menu, the skills
# root is seeded like a built-in's, and parents' skill trees are seeded first.
# The stage/checklist contract itself is argus/core/vertical_contract.py.
ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_ROUTING_PATH = ("hardware", "chip_design")
VERTICAL_PURPOSE = (
    "digital ASIC/hardware accelerator subsystems: workload, microarchitecture, compute, "
    "memory/DMA, interconnect and host integration; bounded APB4 register/timer/interrupt "
    "control design, repair and diagnosis. For the fixed apb4-timer-v1 contract, the control "
    "profile already includes authorized RTL repair, native synthesis, both RTL/synthesized "
    "simulations and generic-cell limits within verification; these generic counts are not "
    "PPA and do not require custom rtl+ppa stages. Other requests use scoped architecture/RTL/PPA tasks "
    "or explicit full implementation and sign-off, not GPU software kernels"
)
VERTICAL_SKILLS = Path(__file__).resolve().parent / "skills"
VERTICAL_SKILL_PARENTS: tuple[str, ...] = ("digital_circuit",)

STAGE_ORDER = (
    "definition",
    "architecture",
    "environment",
    "rtl",
    "verification",
    "ppa",
    "prototype",
    "benchmark",
    "signoff",
)
CHECKLIST_STAGE_ORDER = STAGE_ORDER
# Stage order remains strict, but accepted upstream evidence is reusable. An
# operator-boundary uplift normally reopens RTL, not the unchanged product,
# architecture, and toolchain contracts.
WORKFLOW_MODE = "proportional"
completion_gate = "metric"
# Round guards (Argus core/round_policy.py; an Argus without per-vertical round
# policies ignores this). ASIC/subsystem work is gated by simulation, synthesis
# and control-contract checks; a failing native check followed by several
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
    "architecture": {
        "purpose": "workload and subsystem architecture study; no RTL/PPA/physical implementation claim",
        "stages": ("definition", "architecture"),
    },
    "rtl": {
        "purpose": "design and verify accelerator RTL; target technology is planned, not physically certified",
        "stages": ("definition", "architecture", "environment", "rtl", "verification"),
    },
    "verification": {
        "purpose": "independently verify an existing chip subsystem against its frozen contract",
        "stages": ("verification",),
    },
    "control": {
        "purpose": "bounded APB4 register/timer/interrupt RTL design, authorized repair or diagnosis against original inputs; native RTL and synthesized simulation plus generic cell limits, not physical PPA",
        "stages": ("verification",),
    },
    "ppa": {
        "purpose": "verify and measure an existing design's PPA; no prototype or final implementation claim",
        "stages": ("verification", "ppa"),
    },
    "prototype": {
        "purpose": "verify, measure PPA and demonstrate an existing design at its declared prototype level",
        "stages": ("verification", "ppa", "prototype"),
    },
    "benchmark": {
        "purpose": "verify and fairly benchmark an existing design with current PPA evidence",
        "stages": ("verification", "ppa", "benchmark"),
    },
    "full": {
        "purpose": "explicit full chip workflow through prototype, benchmark and final target-level review",
        "stages": STAGE_ORDER,
    },
}
WORKFLOW_STAGE_REQUIREMENTS = {
    "definition": (),
    "architecture": ("definition",),
    "environment": (),
    "rtl": ("architecture", "environment", "verification"),
    "verification": (),
    "ppa": ("verification",),
    "prototype": ("ppa",),
    "benchmark": ("ppa",),
    "signoff": STAGE_ORDER[:-1],
}

CHECKLIST_ITEMS: dict[str, tuple[ChecklistItem, ...]] = {
    "definition": (
        ChecklistItem(
            id="definition.delivery-scope",
            statement=(
                "The delivery level, target workload, supported/non-supported operations, numerical "
                "formats, interfaces, target platform/technology, and non-goals are frozen."
            ),
            evidence_hint="design/CHIP_SCOPE.json and design/WORKLOAD.md",
        ),
        ChecklistItem(
            id="definition.acceptance-metrics",
            statement=(
                "The correctness, performance, power, area/resource, quality, and provenance "
                "standards the result must meet are measurable and distinguish IP, FPGA, GDS, "
                "tapeout, and market claims."
            ),
            evidence_hint="design/CHIP_SCOPE.json acceptance_metrics and design/SPEC.md",
        ),
        ChecklistItem(
            id="definition.baseline-fairness",
            statement=(
                "Open-hardware, software/system, and market-reference baselines are named with an "
                "explicit apples-to-apples comparison policy."
            ),
            evidence_hint="design/BASELINE_PLAN.md or a definition-stage baseline section",
        ),
    ),
    "architecture": (
        ChecklistItem(
            id="architecture.compute-memory-model",
            statement=(
                "Compute, dataflow, memory hierarchy, DMA/NoC, external bandwidth, arithmetic intensity, "
                "and expected utilization are quantified for representative workload shapes."
            ),
            evidence_hint="design/ARCHITECTURE.md and design/MEMORY_MODEL.json",
        ),
        ChecklistItem(
            id="architecture.interface-control",
            statement=(
                "Host commands, register map, address/stride rules, interrupts, errors, reset/clock/CDC, "
                "backpressure, latency, and completion semantics are explicit."
            ),
            evidence_hint="design/SPEC.md interface and cycle tables",
        ),
        ChecklistItem(
            id="architecture.leverage-risk",
            statement=(
                "Amdahl/roofline leverage, implementation risks, IP reuse, verification strategy, and "
                "fallback or de-scoping decisions are recorded before RTL."
            ),
            evidence_hint="design/ARCHITECTURE.md design-tradeoff table",
        ),
        ChecklistItem(
            id="architecture.area-reuse-plan",
            statement=(
                "Area reuse is planned explicitly: mutually exclusive operators share or fold "
                "MACs, accumulators, requantization, vector/SFU, divide/round/saturate, DMA, "
                "buffers, and control where measured mux/control overhead preserves the PPA goal."
            ),
            evidence_hint=(
                "design/ARCHITECTURE.md lifetime/resource-sharing table with dedicated-versus-"
                "shared alternatives and expected cycle/area costs"
            ),
        ),
    ),
    "environment": (
        ChecklistItem(
            id="environment.eda-capabilities",
            statement=(
                "A machine-readable record proves that the simulator, formal, synthesis, FPGA, "
                "physical-design, PDK, and compiler/runtime capabilities and the sign-off checks "
                "the active workflow profile and delivery level require are all ready. "
                "The rtl profile requires simulation and lint, not omitted implementation tools."
            ),
            evidence_hint="research/ENVIRONMENT_AUDIT.json",
        ),
        ChecklistItem(
            id="environment.tool-ip-selection",
            statement=(
                "Maintained tools, reusable IP, licenses, PDKs, board support, and canonical flows were "
                "queried and selected before custom infrastructure was authored."
            ),
            evidence_hint="research/TOOLCHAIN_CANDIDATES.md and research/IP_REUSE_PLAN.md",
        ),
    ),
    "rtl": (
        ChecklistItem(
            id="rtl.contract-traceability",
            statement=(
                "Every synthesizable module and generated source traces to architecture/spec requirements "
                "and exactly matches the RTL manifest interfaces and parameters."
            ),
            evidence_hint="design/RTL_MANIFEST.json and RTL traceability notes",
        ),
        ChecklistItem(
            id="rtl.hardware-discipline",
            statement=(
                "RTL has intentional widths/signedness, complete combinational assignments, disciplined "
                "sequential logic, safe clock/reset/CDC behavior, bounded arrays/counters, and no "
                "unexplained latches, multiple drivers, or simulation-only design constructs."
            ),
            evidence_hint="lint/elaboration output and reviewer inspection",
        ),
        ChecklistItem(
            id="rtl.ip-provenance",
            statement=(
                "Third-party and generated IP have pinned source revisions, compatible licenses, wrappers, "
                "configuration, and regeneration commands."
            ),
            evidence_hint="design/RTL_MANIFEST.json provenance entries",
        ),
    ),
    "verification": (
        ChecklistItem(
            id="verification.independent-oracle",
            statement=(
                "RTL outputs and state transitions are checked against an independent executable reference "
                "or formally specified properties, including numerical tolerances and quality constraints."
            ),
            evidence_hint="verification/PLAN.md, reference/, formal/, and verification/RESULTS.json; control profile uses CONTROL_PLAN.json and control/ASSESSMENT.json",
        ),
        ChecklistItem(
            id="verification.coverage-stress",
            statement=(
                "Unit/integration, reset, boundary, stalls/backpressure, illegal/error, randomized, CDC, "
                "X/Z, overflow, and representative workload cases meet declared coverage goals."
            ),
            evidence_hint="verification/RESULTS.json coverage and scenario summaries",
        ),
        ChecklistItem(
            id="verification.reproducible-green",
            statement=(
                "Fresh simulator/formal commands exit successfully, the referenced raw files exist, "
                "and passing summaries contain no contradictory failures. A control-profile "
                "diagnosis may retain real failures; control design/repair must pass both RTL and synthesized simulation."
            ),
            evidence_hint="verification/RESULTS.json and verification/raw/; control profile uses verification/control/ and the Engineer-authored verification/CONTROL_REVIEW.md",
        ),
    ),
    "ppa": (
        ChecklistItem(
            id="ppa.constraints-and-provenance",
            statement=(
                "Target technology/device, tools, libraries/PDK, clocks, I/O constraints, memory treatment, "
                "parameters, corners, activity, and raw report paths are pinned."
            ),
            evidence_hint="ppa/PROTOCOL.md and ppa/RESULTS.json",
        ),
        ChecklistItem(
            id="ppa.timing-area-power",
            statement=(
                "Fresh timing/Fmax, area/resources including memory, power/energy methodology, utilization, "
                "warnings, and uncertainty are reported for the candidate and fair baselines."
            ),
            evidence_hint="ppa/RESULTS.json and ppa/raw/",
        ),
        ChecklistItem(
            id="ppa.physical-closure",
            statement=(
                "When physical design or GDS is claimed, placement/routing, congestion, STA, DRC, LVS, "
                "antenna, density, and generated-layout provenance satisfy the declared closure level."
            ),
            evidence_hint="ppa/RESULTS.json physical_closure and physical/raw/",
        ),
        ChecklistItem(
            id="ppa.incremental-area-reserve",
            statement=(
                "Every architecture frontier reports non-SRAM delta area/cells, Fmax, cycles, "
                "and remaining area reserve; repeated low-yield local tweaks stop and escalate "
                "to structural folding or an explicit Pareto characterization."
            ),
            evidence_hint="append-only PPA frontier ledger bound to RTL and constraint hashes",
        ),
    ),
    "prototype": (
        ChecklistItem(
            id="prototype.delivery-level",
            statement=(
                "The declared FPGA, emulator, GDS, silicon, or structured N/A prototype level is consistent "
                "with the frozen chip scope and contains no broader hardware claim."
            ),
            evidence_hint="prototype/RESULTS.json",
        ),
        ChecklistItem(
            id="prototype.hardware-evidence",
            statement=(
                "Applicable prototype evidence records tool/board/chip identity, the build output, clocks and "
                "resources, host/runtime integration, on-hardware correctness, power, and raw commands/logs."
            ),
            evidence_hint="prototype/RESULTS.json and prototype/raw/",
        ),
    ),
    "benchmark": (
        ChecklistItem(
            id="benchmark.protocol-fairness",
            statement=(
                "Candidate and baselines use identical workloads, quantization/quality, memory/host budgets, "
                "warmup, repetitions, synchronization, power method, and platform/technology constraints."
            ),
            evidence_hint="benchmark/PROTOCOL.md",
        ),
        ChecklistItem(
            id="benchmark.kernel-system-metrics",
            statement=(
                "Kernel and end-to-end results separately report latency/throughput, effective bandwidth and "
                "utilization, energy, area/resources, uncertainty, and workload-specific metrics."
            ),
            evidence_hint="benchmark/RESULTS.json and benchmark/raw/",
        ),
        ChecklistItem(
            id="benchmark.claim-boundary",
            statement=(
                "All regressions, unsupported cases, quality deltas, and market-reference limitations are "
                "explicit; different PDK nodes or commercial products are not presented as direct PPA wins."
            ),
            evidence_hint="benchmark/RESULTS.json limitations and comparison_scope",
        ),
    ),
    "signoff": (
        ChecklistItem(
            id="signoff.artifact-integrity",
            statement=(
                "The final manifest links source, generated files, verification, PPA, prototype, "
                "benchmark, tool versions, git identity, and reproduction entry points."
            ),
            evidence_hint="signoff/ARTIFACT_MANIFEST.json and signoff/SIGNOFF.json",
        ),
        ChecklistItem(
            id="signoff.provenance-autonomy",
            statement=(
                "IP/license provenance, Argus role trajectories, intervention history, failed attempts, and "
                "independent Reviewer decisions support the stated autonomy claim."
            ),
            evidence_hint="signoff/SIGNOFF.json provenance and intervention records",
        ),
        ChecklistItem(
            id="signoff.bounded-result",
            statement=(
                "RESULTS.md is reproducible and limits claims to the certified delivery level, hardware, "
                "technology, workloads, quality, PPA, and benchmark evidence."
            ),
            evidence_hint="RESULTS.md and signoff/SIGNOFF.json",
        ),
    ),
}


def stage_completion_issues(
    stage: str, project_root: Path, *, workflow_profile: str = "full",
    workflow_stages: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return deterministic issues from the vertical's existing validators."""
    stage_name = (stage or "").strip().lower()
    root = Path(project_root)

    if workflow_profile == "control":
        from argus_verticals.hardware.shared.evidence import EvidenceError as ControlEvidenceError

        if stage_name != "verification":
            return ("control profile only executes its bounded verification stage",)
        try:
            validate_completion(root)
        except ControlEvidenceError as exc:
            return (str(exc),)
        return ()

    if stage_name == "environment":
        from .environment_audit import check

        _ok, errors = check(
            root, workflow_profile=workflow_profile, workflow_stages=workflow_stages,
        )
        target = root / "design" / "TARGET.json"
        if not target.is_file() or target.stat().st_size == 0:
            errors.append("environment requires a non-empty design/TARGET.json")
        return tuple(errors)

    validator_name = {
        "definition": "scope",
        "architecture": "architecture",
        "rtl": "rtl",
        "verification": "verification",
        "ppa": "ppa",
        "prototype": "prototype",
        "benchmark": "benchmark",
        "signoff": "signoff",
    }.get(stage_name)
    if validator_name is None:
        return ()

    from .evidence import VALIDATORS, EvidenceError, _signoff

    issues: list[str] = []
    try:
        if workflow_profile == "custom" and stage_name == "verification":
            VALIDATORS["rtl"](root)
        if stage_name == "signoff":
            _signoff(root, workflow_profile=workflow_profile, workflow_stages=workflow_stages)
        else:
            VALIDATORS[validator_name](root)
    except EvidenceError as exc:
        issues.append(str(exc))

    if stage_name == "definition":
        for relative in ("design/WORKLOAD.md", "design/SPEC.md"):
            path = root / relative
            if not path.is_file() or path.stat().st_size == 0:
                issues.append(f"definition requires a non-empty {relative}")
    return tuple(issues)


def control_check_command() -> str:
    script = (
        "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
        "contract = load_vertical_contract('chip_design').for_profile('control'); "
        "issues = contract.completion_issues('verification', Path.cwd()); "
        "print(list(issues)); raise SystemExit(bool(issues))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def render_role_prompt_fragment(
    *, role: str, operation: str, stage: str, scope: str, project_root: Path | None,
) -> str:
    if stage != "verification":
        return ""
    from argus.core.pipeline_state import read_pipeline_state

    if project_root is None or read_pipeline_state(project_root).get("workflow_profile") != "control":
        return (
            "Existing accelerator verification retains its original source-bound verification schema; "
            "do not substitute the APB4 control adapter or invent physical results.\n\n"
            + verification_review_contract()
            + "\n" + Path(__file__).with_name("verification-contract.md").read_text(encoding="utf-8")
            + "\nFor Engineer debugging or an execution-capable operator, the legacy record check is:\n"
            f"```bash\n{evidence_check_command('chip_design', stage)}\n```\n"
            "The host uses the saved profile, including any custom RTL-manifest requirements; "
            "the standalone legacy check is not approval of that composed scope.\n"
        )
    script = (
        "from pathlib import Path; from argus.verticals._base import load_vertical_contract; "
        "load_vertical_contract('chip_design'); "
        "from argus_verticals.chip_design.control import run; run(Path.cwd())"
    )
    return (
        "Only for the selected control profile, use this original-input contract. "
        "Legacy accelerator verification uses its existing evidence requirements.\n\n"
        + Path(__file__).with_name("control-contract.md").read_text(encoding="utf-8")
        + "\nEngineer: execute the native study from the execution project, not session state:\n"
        f"```bash\n{shlex.quote(sys.executable)} -c {shlex.quote(script)}\n```\n"
        "Engineer: before requesting review, author verification/CONTROL_REVIEW.md with all four "
        "required sections and the exact measured JSON summary. The runner does not write or approve "
        "your report. Reviewer does not author missing Engineer reports. "
        "Reviewer: inspect original requirements, raw evidence, the Engineer's report and authorized repair changes. "
        "The host runs the profile-specific read-only checker before review and provides its current result "
        "as raw evidence. Use that host evidence, not Engineer testimony; your read/search-only tools need "
        "no shell permission. Missing or failed host evidence remains incomplete, and must not be replaced "
        "by an Engineer-authored Reviewer execution record. Do not request a separate validation-only task. "
        "For Engineer debugging or an execution-capable operator, the equivalent command is:\n"
        f"```bash\n{control_check_command()}\n```\n"
        "Manager/Planner preserve all original constraints. Design/repair must pass; "
        "only an originally requested diagnose goal may conclude with engineering failure. "
        "Neither passing RTL alone nor generic synthesis statistics establish physical PPA.\n"
    )


def role_banner(role: str) -> str:
    """Frame roles around auditable chip-design evidence."""
    common = (
        "MISSION TYPE: CHIP / ACCELERATOR DESIGN. Each claim requires checkable "
        "evidence. Use the active workflow profile: architecture, RTL, verification, "
        "PPA, prototype, benchmark, bounded APB4 control, or explicitly full design. If no profile was saved, "
        "preserve the legacy full flow. Do not demand outputs from omitted stages. "
        "For the fixed apb4-timer-v1 peripheral contract, control is a self-contained "
        "implementation/repair and native verification profile, not verification-only reuse. "
        "Generic synthesis cell counts do not request a separate PPA stage. "
        "This is NOT ordinary software work or GPU kernel programming. "
        "Delivery level describes the target; only completed, reviewed stages may "
        "be claimed as delivered. "
        "synthesizable IP, FPGA, open-PDK GDS, computer-verified pre-tapeout readiness, "
        "actual tapeout readiness, and fabricated silicon "
        "are different claims. Freeze interfaces, numerical behavior, target technology, "
        "resource/power budgets, baselines, and the metrics the finished design must "
        "meet before implementation. "
        "Numeric area, frequency, power, memory, and quality targets are operator-owned "
        "contracts. An Agent-authored plan, ledger, or review may "
        "recommend a change but cannot authorize one; relaxing a target requires explicit "
        "operator approval recorded as such. "
        "Use maintained EDA flows and IP before authoring replacements. Never invent tool "
        "runs, coverage, PPA, power, DRC/LVS/STA, FPGA, silicon, or market-comparison results.\n"
    )
    normalized = (role or "").strip().lower()
    if normalized == "manager":
        return common + (
            "Reuse Reviewer-certified upstream stages and roll back only to the earliest "
            "stage whose contract actually changed. Advancing the first unsupported "
            "operator within an unchanged workload, delivery level, numerical contract, "
            "host/memory interface, resource budget, architecture, target technology, and "
            "toolchain is an RTL delta: roll back directly to rtl. Roll back to definition "
            "only for a real workload/delivery/interface/budget contract change; architecture "
            "only for a changed dataflow, memory hierarchy, compute organization, or control "
            "interface; environment only for changed target/tool/IP/license requirements. "
            "Never treat a Planner or Reviewer budget-reallocation proposal as operator "
            "authorization to relax a numeric target. "
            "Do not rewrite, rehash, or recertify stable definition/architecture/environment "
            "records merely to replace the name of the next unsupported operator. When several "
            "remaining operators share one descriptor family, numerical contract, memory model, "
            "and compute organization, freeze that family once instead of reopening one contract "
            "per operator. After that family contract is certified, keep resource folding, "
            "retiming, and area/timing repair in the RTL loop; do not reopen earlier stages. Use a fast "
            "capability loop for non-milestone operator uplifts: rtl -> verification -> fresh "
            "target-matched PPA when included in scope, inside one bounded RTL mission whose Planner task has "
            "`stage_closing=false`; a Reviewer judgment that the work holds completes that task "
            "but does not advance the flow out of rtl. Then schedule the next operator directly. Run prototype, "
            "full benchmark, multi-node PPA, the signoff stage, and a local milestone commit only when "
            "the complete target hardware workload or complete model/system demonstration is "
            "Reviewer-certified, or the operator explicitly requests a release. Intermediate "
            "operator groups such as QKV, RoPE+KV, Attention, or MLP are checkpoints, not release "
            "milestones. Every reused result must still "
            "bind the current design/RTL_MANIFEST.json source revision; stale bindings are never reusable."
        )
    if normalized == "planner":
        return common + (
            "Plan from highest-risk unknowns and the declared delivery level. Close workload/"
            "interface/quality ambiguity before architecture; close EDA/PDK/IP/license readiness "
            "before RTL; require independent verification before PPA; and require PPA/prototype "
            "evidence before benchmark claims. Rank architecture changes by roofline/Amdahl "
            "leverage and end-to-end workload impact. Separate fair same-flow open baselines from "
            "commercial market context. Replan when toolchain, correctness, timing, area, power, or "
            "memory bandwidth stands in the way rather than polishing downstream reports."
            " Batch the remaining operators of one already-understood hardware family into one "
            "definition/architecture contract; never schedule per-operator environment refreshes "
            "when target, tools, IP, licenses, and delivery level are unchanged."
            " For a non-milestone operator uplift, plan rtl -> verification and, when "
            "included in scope, target-matched PPA as exactly one bounded RTL task with `stage_closing=false`; include "
            "implementation, full regression, canonical PPA, and evidence binding in that task. "
            "Do not emit separate verification-stage or PPA-stage closeout tasks and do not ask "
            "the Manager to advance out of rtl. Leave prototype, full benchmark, and the signoff "
            "stage for complete-workload or "
            "model/system release milestones. Keep an unmet operator-owned target unmet "
            "until the operator explicitly approves a replacement; do not route "
            "implementation through a proposed cap."
        )
    if normalized == "engineer":
        return common + (
            "Read the project's own terms and inspect the exact runtime first. Build the smallest "
            "traceable architecture/RTL increment, maintain an independent executable model, and "
            "run real lint, simulation, formal, synthesis, implementation, and benchmark commands "
            "appropriate to scope. Preserve failing seeds, waveforms, reports, candidate diffs, "
            "tool versions, constraints, and PDK/board identity. Fix design/source rather than "
            "weakening tests or constraints. Keep generated outputs separate from authored source."
        )
    if normalized == "reviewer":
        return common + (
            "Act as an independent architecture, verification, implementation, benchmark, and "
            "tapeout-readiness reviewer. Inspect decisive execution evidence; challenge workload and memory "
            "assumptions, reference independence, CDC/reset/protocol behavior, timing/area/power "
            "constraints, baseline fairness, quality floors, IP licensing, raw file hashes, "
            "and intervention claims. Decline different-node PPA comparisons, simulation presented "
            "as silicon, or commercial-product claims without same-workload measured evidence."
            " Turn back any claimed target relaxation that lacks explicit operator authorization; "
            "the Reviewer's judgment alone cannot change an operator-owned numeric target. "
            " Reuse upstream evidence only when its recorded RTL-manifest binding is current. "
            "Treat one successful canonical, hash-bound Yosys/ABC result as the decisive PPA "
            "run: inspect its raw evidence and do not launch a second full Yosys/ABC PPA for "
            "the same RTL, verification, constraints, library, and toolchain hashes unless "
            "that evidence is incomplete or materially suspect. "
            "For intermediate operator and operator-group uplifts, certify the "
            "rtl/verification/PPA delta without demanding ceremonial prototype N/A, full "
            "benchmark, multi-node PPA, or a rerun of the signoff stage. Treat `done` on such a "
            "`stage_closing=false` task as mission completion, not permission to advance the "
            "flow out of rtl."
        )
    return common
