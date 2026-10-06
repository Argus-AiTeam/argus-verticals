"""Separate native control evidence from the Engineer's final report delivery."""
from __future__ import annotations

import json
import re
from pathlib import Path

from argus.core.pipeline_state import read_pipeline_state
from argus.engineer.round_evidence import (
    RoundEvidence,
    RoundEvidenceRequest,
    register_round_evidence_provider,
)

from argus_verticals.hardware.shared.evidence import EvidenceError, project_file, record

from . import control
from .control_model import ASSESSMENT, PLAN, resolve

REPORT = "verification/CONTROL_REVIEW.md"
SECTIONS = ("Scope", "Findings and changes", "Evidence", "Limitations")


def summary(root: Path, measured: dict | None = None) -> dict:
    """Return report facts, not an approval or a substitute for native validation."""
    spec, _ = resolve(root)
    if measured is None:
        measured = record(root, ASSESSMENT)
    try:
        configurations = {}
        for name, parameters in spec["configurations"].items():
            row = measured["configurations"][name]
            simulations = {}
            for model, simulation in row["simulations"].items():
                simulations[model] = {
                    "samples": simulation["samples"],
                    "comparisons": sum(c["comparisons"] for c in simulation["checks"].values()),
                    "mismatches": sum(c["mismatches"] for c in simulation["checks"].values()),
                    "reference_event_counts": simulation["coverage"]["reference_event_counts"],
                    "completed_write_strobes": simulation["coverage"]["completed_write_strobes"],
                }
            configurations[name] = {
                "parameters": parameters,
                "generic_cells": row["synthesis"]["generic_cells"],
                "headroom_cells": row["synthesis"]["headroom_cells"],
                "simulations": simulations,
            }
        return {
            "specification": record(root, PLAN)["specification"],
            **{key: spec[key] for key in ("contract", "goal", "top", "sources", "base_address", "max_generic_cells", "limitations")},
            "engineering_status": measured["status"],
            "configurations": configurations,
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise EvidenceError(f"{REPORT}: cannot summarize incomplete native assessment: {exc}") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceError(f"{REPORT}: duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read_report(root: Path) -> tuple[bytes, str]:
    path = project_file(root, REPORT)
    if path.stat().st_size > 65536:
        raise EvidenceError(f"{REPORT}: report exceeds 64 KiB")
    try:
        original = path.read_bytes()
        text = original.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"{REPORT}: cannot read report: {exc}") from exc
    sections: dict[str, list[str]] = {}
    current = None
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            title = line[3:].strip()
            if title not in SECTIONS or title in sections:
                raise EvidenceError(f"{REPORT}: unexpected or repeated section {title!r}")
            current = title
            sections[title] = []
        elif current is not None:
            sections[current].append(line)
    if fenced or set(sections) != set(SECTIONS):
        raise EvidenceError(f"{REPORT}: requires sections {', '.join(SECTIONS)} and closed code fences")
    for title in ("Scope", "Findings and changes", "Limitations"):
        prose = re.sub(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$", "", "\n".join(sections[title]))
        if not any(line.strip() and not line.lstrip().startswith("#") for line in prose.splitlines()):
            raise EvidenceError(f"{REPORT}: {title} requires Engineer-authored prose")
    evidence = re.fullmatch(r"\s*```json[ \t]*\n(.*?)\n```[ \t]*\s*", "\n".join(sections["Evidence"]), re.DOTALL)
    if evidence is None:
        raise EvidenceError(f"{REPORT}: Evidence must contain exactly one JSON summary block")
    try:
        payload = json.loads(evidence[1], object_pairs_hook=_unique_object)
        canonical = json.dumps(payload, sort_keys=True, allow_nan=False)
    except (json.JSONDecodeError, ValueError) as exc:
        raise EvidenceError(f"{REPORT}: invalid JSON summary: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvidenceError(f"{REPORT}: summary must be a JSON object")
    return original, canonical


def validate_completion(root: Path) -> dict:
    original, report = _read_report(root)
    measured = control.validate(root)
    if report != json.dumps(summary(root, measured), sort_keys=True, allow_nan=False):
        raise EvidenceError(f"{REPORT}: summary differs from the original specification or independently replayed evidence")
    try:
        if project_file(root, REPORT).read_bytes() != original:
            raise EvidenceError(f"{REPORT}: report changed during final validation")
    except OSError as exc:
        raise EvidenceError(f"{REPORT}: cannot recheck report: {exc}") from exc
    return measured


@register_round_evidence_provider
def round_evidence(request: RoundEvidenceRequest) -> RoundEvidence | None:
    # Both mission handoffs/<id> and the standalone .argus/life root are two levels below state.
    pipeline = read_pipeline_state(request.life_dir.parent.parent)
    if pipeline.get("vertical") != "chip_design" or pipeline.get("workflow_profile") != "control":
        return None
    title = "Host-executed control completion check (not Engineer testimony or Reviewer approval)"
    try:
        measured = validate_completion(request.workdir)
    except (EvidenceError, OSError) as exc:
        issue = f"Control completion check failed: {exc}"
        return RoundEvidence(reviewer_text=f"{title}\n{issue}", engineer_note=issue)
    return RoundEvidence(
        reviewer_text=f"{title}\n"
        + json.dumps({"issues": [], **summary(request.workdir, measured)}, indent=2)
        + "\nThe host independently replayed current native evidence and checked the report. "
        "Reviewer still judges original constraints, source changes and narrative; no Reviewer shell is required.",
    )
