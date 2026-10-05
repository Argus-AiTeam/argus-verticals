"""Host evidence for existing hardware checks, without replaying recorded commands."""
from __future__ import annotations

import json
from pathlib import Path

from argus.core.pipeline_state import read_pipeline_state
from argus.engineer.round_evidence import (
    RoundEvidence,
    RoundEvidenceRequest,
    register_round_evidence_provider,
)

_STAGES = {
    "chip_design": {"verification"},
    "digital_circuit": {"verification"},
    "digital_circuit_verification": {"plan", "simulation", "formal", "review"},
    "fpga_design": {"requirements", "rtl", "verification", "implementation", "bringup", "delivery"},
    "analog_mixed_signal": {"specification", "model", "simulation", "review"},
    "rf_design": {"specification", "model", "analysis", "review"},
    "pcb_design": {"specification", "design", "verification", "review"},
    "package_design": {"specification", "model", "thermal", "review"},
    "power_electronics": {"specification", "model", "simulation", "review"},
}


def hardware_review_contract() -> str:
    return Path(__file__).with_name("hardware-review.md").read_text(encoding="utf-8")


def verification_review_contract() -> str:
    return hardware_review_contract() + "\n" + Path(__file__).with_name("verification-review.md").read_text(encoding="utf-8")


@register_round_evidence_provider
def round_evidence(request: RoundEvidenceRequest) -> RoundEvidence | None:
    # Mission handoffs/<id> and standalone .argus/life are both two levels below state.
    state_root = request.life_dir.parent.parent
    pipeline = read_pipeline_state(state_root)
    vertical, stage = pipeline.get("vertical"), pipeline.get("current_stage")
    if stage not in _STAGES.get(vertical, set()):
        return None
    if vertical == "chip_design" and pipeline.get("workflow_profile") == "control":
        return None

    from argus.verticals._base import load_vertical_contract

    try:
        contract = load_vertical_contract(vertical, project_root=state_root)
        if stage not in contract.stage_order:
            raise ValueError(f"{stage}: not in the saved workflow scope")
        issues = contract.completion_issues(stage, request.workdir, state_root=state_root)
    except (OSError, ValueError) as exc:
        issues = (f"completion checker unavailable: {exc}",)
    result = {
        "vertical": vertical, "workflow_profile": pipeline.get("workflow_profile") or "full",
        "stage": stage, "execution_project": str(request.workdir), "issues": list(issues),
    }
    return RoundEvidence(
        reviewer_text="Host-executed hardware evidence check (not Reviewer approval)\n"
        + json.dumps(result, indent=2)
        + "\nThis is the selected provider's deterministic completion check. Record consistency "
        "does not prove oracle independence, log authenticity, scientific success or broader coverage. "
        "Recorded command arguments were not replayed; only explicitly composed, provider-owned "
        "bounded native adapters can perform their defined replay. No project science entry or claim "
        "was authorized by this check. Reviewer must inspect the actual source and original contract.",
        engineer_note="Host completion issues: " + "; ".join(issues) if issues else "",
    )
