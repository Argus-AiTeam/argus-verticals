"""Literary-editing checks on a project's editor/ folder.

edit:   editor/edited.txt is non-empty and keeps every editor/edit_brief.json must_keep segment verbatim
        (whitespace-normalized). Whether the edit is good or stayed within its mode is the Reviewer's call.
review: editor/review.json is a valid {verdict, findings[]} review in the editor vocabulary; on success
        prints the revision plan (blocking findings first, then by severity) as JSON.
Exit 0 when the check passes; 1 with the issues on stderr (review stops at the first).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EDITOR_MODES = ("rewrite", "expand", "polish", "proofread", "critique")
#: Machine edit-discipline types (blocking) plus live-reviewer craft types (non-blocking).
EDITOR_FINDING_TYPES = frozenset({
    "must_not_break", "empty", "edit_quality", "fact_fidelity", "coherence", "over_reach",
})
SEVERITIES = ("critical", "major", "minor", "note")
_REQUIRED_TEXT = ("id", "type", "location", "evidence", "suggested_action")
_FINDING_KEYS = frozenset(_REQUIRED_TEXT) | {
    "severity", "blocking", "violated_constraint", "must_not_break", "confidence",
}


def _norm(text: str) -> str:
    return " ".join(text.split())


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def edit_issues(project_root: Path) -> list[str]:
    """Issues for unreadable inputs, empty output, or a dropped must-keep segment."""
    editor = project_root / "editor"
    try:
        (editor / "source.txt").read_text(encoding="utf-8")
        edited = (editor / "edited.txt").read_text(encoding="utf-8")
        brief = json.loads((editor / "edit_brief.json").read_text(encoding="utf-8"))
        mode = brief.get("mode") if isinstance(brief, dict) else None
        if mode not in EDITOR_MODES:
            raise ValueError(f"edit_brief.json needs a mode in {list(EDITOR_MODES)}, got {mode!r}")
        must_keep = brief.get("must_keep") or []
        if not _strings(must_keep):
            raise ValueError("edit_brief.json must_keep must be a list of strings")
    except (OSError, ValueError) as exc:
        return [f"literary editor inputs invalid: {exc}"]
    if not edited.strip():
        return ["edited text is empty"]
    kept = _norm(edited)
    return [f"must-keep segment dropped: {seg[:40]!r}"
            for seg in must_keep if _norm(seg) and _norm(seg) not in kept]


def _finding_issue(index: int, finding: Any) -> str | None:
    if not isinstance(finding, dict):
        return f"finding {index} must be an object"
    where = f"finding {finding.get('id', index)!r}"
    stray = sorted(set(finding) - _FINDING_KEYS)
    if stray:
        return f"{where}: unexpected key(s) {stray}"
    for key in _REQUIRED_TEXT:
        if not isinstance(finding.get(key), str) or not finding[key]:
            return f"{where}: {key} must be a non-empty string"
    if finding.get("severity") not in SEVERITIES:
        return f"{where}: severity must be one of {list(SEVERITIES)}"
    if not isinstance(finding.get("blocking"), bool):
        return f"{where}: blocking must be true or false"
    if not isinstance(finding["violated_constraint"], str):
        return f"{where}: violated_constraint must be a string"
    if not _strings(finding["must_not_break"]):
        return f"{where}: must_not_break must be a list of strings"
    confidence = finding.get("confidence", 0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return f"{where}: confidence must be a number from 0 to 1"
    if finding["type"] not in EDITOR_FINDING_TYPES:
        return f"{where}: unknown type {finding['type']!r} (vocabulary: {sorted(EDITOR_FINDING_TYPES)})"
    return None


def normalize_review(raw: Any) -> dict[str, Any]:
    """Fill finding defaults, then validate structure and verdict coherence; raise ValueError on the first issue."""
    if not isinstance(raw, dict):
        raise ValueError("review must be a JSON object")
    review = {"findings": [], **raw}
    stray = sorted(set(review) - {"verdict", "findings"})
    if stray:
        raise ValueError(f"review has unexpected key(s) {stray}")
    if review.get("verdict") not in ("revise", "done"):
        raise ValueError("verdict must be 'revise' or 'done'")
    if not isinstance(review["findings"], list):
        raise ValueError("findings must be an array")
    findings = []
    for index, raw_finding in enumerate(review["findings"]):
        finding = raw_finding
        if isinstance(raw_finding, dict):
            finding = {"must_not_break": [], "violated_constraint": "", **raw_finding}
            # Models often number findings 1, 2, ...; accept that as the string id.
            if isinstance(finding.get("id"), (int, float)) and not isinstance(finding["id"], bool):
                finding["id"] = str(finding["id"])
        issue = _finding_issue(index, finding)
        if issue:
            raise ValueError(issue)
        findings.append(finding)
    if any(f["blocking"] for f in findings) and review["verdict"] != "revise":
        raise ValueError("a blocking finding stands but verdict is not 'revise'")
    if not findings and review["verdict"] != "done":
        raise ValueError("no findings but verdict is not 'done' - nothing to revise")
    return {"verdict": review["verdict"], "findings": findings}


def revision_plan(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Blocking findings first, then by descending severity; each carries its fix and must-not-break invariants."""
    ordered = sorted(review["findings"], key=lambda f: (not f["blocking"], SEVERITIES.index(f["severity"])))
    return [{"finding_id": f["id"], "type": f["type"], "severity": f["severity"], "blocking": f["blocking"],
             "location": f["location"], "suggested_action": f["suggested_action"],
             "must_not_break": list(f["must_not_break"])} for f in ordered]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edit_check.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=["edit", "review"],
                        help="edit: edited.txt against edit_brief.json; review: validate review.json, print the plan")
    parser.add_argument("--project-root", default=".", help="project workspace holding editor/ (default: .)")
    args = parser.parse_args(argv)
    root = Path(args.project_root)
    if args.check == "edit":
        issues = edit_issues(root)
        for issue in issues:
            print(f"FAIL: {issue}", file=sys.stderr)
        if not issues:
            print("OK: editor/edited.txt is non-empty and keeps every must-keep segment")
        return 1 if issues else 0
    try:
        review = normalize_review(json.loads((root / "editor" / "review.json").read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"FAIL: editor/review.json: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(revision_plan(review), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
