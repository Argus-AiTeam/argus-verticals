"""Modern-poetry hard-constraint and review-format checks.

draft   check poetry/draft_poem.txt against poetry/form_spec.json and write poetry/form_report.json
final   check poetry/final_poem.txt against poetry/form_spec.json
review  check poetry/review.json and print its findings in the order to revise them

Only DECLARED hard constraints are machine-checked (language, line count, banned words, non-empty);
imagery, lineation, tone and cliche beyond the list are the reviewer's judgement, never checked here.
Exit 0: no finding / a valid review. Exit 1: each issue is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: The machine-decidable finding types (hard constraints only); always blocking.
FORM_FINDING_TYPES: frozenset[str] = frozenset({"language", "line_count", "banned_word", "empty_line"})
#: Live-reviewer craft types; never blocking, never mechanized.
CRAFT_TYPES: frozenset[str] = frozenset({
    "imagery", "lineation", "tone", "cliche", "coherence", "reference_fidelity",
})
SEVERITIES: tuple[str, ...] = ("critical", "major", "minor", "note")


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _han_ratio(s: str) -> float:
    chars = [c for c in s if not c.isspace()]
    return sum("一" <= c <= "鿿" for c in chars) / len(chars) if chars else 0.0


def _finding(ftype: str, detail: str, line: int | None = None) -> dict[str, Any]:
    return {"type": ftype, "severity": "blocking", "line": line, "detail": detail}


def check_form(text: str, spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return blocking findings where ``text`` violates the declared ``spec``.

    ``spec`` keys (all optional): ``language`` ('zh'|'en'), ``line_count`` (int),
    ``min_lines``, ``max_lines`` (int), ``banned_words`` (list[str]). An empty spec
    means only the always-on non-empty check applies.
    """
    spec = spec or {}
    if not isinstance(spec, dict):
        raise ValueError("form_spec must be an object")
    findings: list[dict[str, Any]] = []
    lines = _lines(text)

    if not lines:
        findings.append(_finding("empty_line", "poem is empty (no non-blank lines)"))
        return findings

    if spec.get("line_count") is not None:
        want = int(spec["line_count"])
        if len(lines) != want:
            findings.append(
                _finding("line_count", f"declared {want} lines but poem has {len(lines)}")
            )
    if spec.get("min_lines") is not None and len(lines) < int(spec["min_lines"]):
        findings.append(
            _finding("line_count", f"poem has {len(lines)} lines, below min {spec['min_lines']}")
        )
    if spec.get("max_lines") is not None and len(lines) > int(spec["max_lines"]):
        findings.append(
            _finding("line_count", f"poem has {len(lines)} lines, above max {spec['max_lines']}")
        )

    lang = spec.get("language")
    if lang == "zh" and _han_ratio(text) < 0.5:
        findings.append(_finding("language", "declared zh but not predominantly Han script"))
    if lang == "en" and _han_ratio(text) > 0.2:
        findings.append(_finding("language", "declared en but contains substantial Han script"))

    banned = [w for w in (spec.get("banned_words") or []) if w]
    for i, ln in enumerate(lines, 1):
        for w in banned:
            if w in ln:
                findings.append(_finding("banned_word", f"banned cliché {w!r} present", i))
    return findings


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def review_issues(review: Any) -> list[str]:
    """Every way ``review`` breaks the review format; empty when it is valid."""
    if not isinstance(review, dict):
        return ["review must be a JSON object"]
    issues = [f"unknown key {key!r}" for key in sorted(set(review) - {"verdict", "findings"})]
    verdict = review.get("verdict")
    if verdict not in ("revise", "done"):
        issues.append("verdict must be 'revise' or 'done'")
    findings = review.get("findings", [])
    if not isinstance(findings, list):
        return issues + ["findings must be an array"]
    for n, f in enumerate(findings, 1):
        if not isinstance(f, dict):
            issues.append(f"finding {n} must be an object")
            continue
        ident = f.get("id")
        where = f"finding {ident if ident is not None else n!r}"
        issues += [f"{where}: unknown key {key!r}" for key in sorted(set(f) - {
            "id", "type", "severity", "blocking", "location", "evidence", "suggested_action",
            "violated_constraint", "must_not_break", "confidence"})]
        if not (_text(ident) or (isinstance(ident, (int, float)) and not isinstance(ident, bool))):
            issues.append(f"{where}: id must be a non-empty string")
        for key in ("location", "evidence", "suggested_action"):
            if not _text(f.get(key)):
                issues.append(f"{where}: {key} must be a non-empty string")
        if f.get("severity") not in SEVERITIES:
            issues.append(f"{where}: severity must be one of {list(SEVERITIES)}")
        if "violated_constraint" in f and not isinstance(f["violated_constraint"], str):
            issues.append(f"{where}: violated_constraint must be a string")
        if "must_not_break" in f and not (isinstance(f["must_not_break"], list)
                                          and all(isinstance(x, str) for x in f["must_not_break"])):
            issues.append(f"{where}: must_not_break must be an array of strings")
        conf = f.get("confidence", 0)
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            issues.append(f"{where}: confidence must be a number from 0 to 1")
        blocking = f.get("blocking")
        if not isinstance(blocking, bool):
            issues.append(f"{where}: blocking must be true or false")
        ftype = f.get("type")
        if not isinstance(ftype, str) or ftype not in FORM_FINDING_TYPES | CRAFT_TYPES:
            issues.append(f"{where}: unknown type {ftype!r} "
                          f"(vocabulary: {sorted(FORM_FINDING_TYPES | CRAFT_TYPES)})")
        elif ftype in FORM_FINDING_TYPES and blocking is False:
            issues.append(f"{where}: hard-constraint finding {ftype!r} must be blocking")
        elif ftype in CRAFT_TYPES and blocking is True:
            issues.append(f"{where}: craft finding {ftype!r} must be non-blocking")
    if any(isinstance(f, dict) and f.get("blocking") is True for f in findings) and verdict != "revise":
        issues.append("a blocking finding stands but verdict is not 'revise'")
    if not findings and verdict != "done":
        issues.append("no findings but verdict is not 'done'")
    return issues


def revision_order(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Findings in the order to revise them: blocking first, then by severity."""
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(review.get("findings", []), key=lambda f: (not f["blocking"], rank[f["severity"]]))


def _check_poem(poetry: Path, which: str) -> int:
    name = f"{which}_poem.txt"
    try:
        if which == "draft":  # no earlier report may outlive a failed run
            (poetry / "form_report.json").unlink(missing_ok=True)
        poem = (poetry / name).read_text(encoding="utf-8")
        spec = json.loads((poetry / "form_spec.json").read_text(encoding="utf-8"))
        findings = check_form(poem, spec)
    except (OSError, ValueError, TypeError) as exc:
        print(f"FAIL: modern poetry inputs invalid: {exc}", file=sys.stderr)
        return 1
    if which == "draft":
        report = {"poem": f"poetry/{name}", "findings": findings}
        (poetry / "form_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for f in findings:
        at = f" (line {f['line']})" if f["line"] else ""
        print(f"FAIL: {f['type']}{at}: {f['detail']}", file=sys.stderr)
    if findings:
        return 1
    print(f"OK: poetry/{name} meets every declared hard constraint")
    return 0


def _check_review(poetry: Path) -> int:
    try:
        review = json.loads((poetry / "review.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL: poetry/review.json unreadable: {exc}", file=sys.stderr)
        return 1
    issues = review_issues(review)
    for issue in issues:
        print(f"FAIL: {issue}", file=sys.stderr)
    if issues:
        return 1
    print(f"OK: poetry/review.json is valid, verdict {review['verdict']!r}")
    for f in revision_order(review):
        keep = f"; must not break: {', '.join(f['must_not_break'])}" if f.get("must_not_break") else ""
        gate = "blocking" if f["blocking"] else "non-blocking"
        print(f"- {f['id']} [{gate}, {f['severity']}, {f['type']}] at {f['location']}: "
              f"{f['suggested_action']}{keep}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="poem_check.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["draft", "final", "review"])
    parser.add_argument("--project-root", default=".", help="project workspace holding poetry/ (default: .)")
    args = parser.parse_args(argv)
    poetry = Path(args.project_root).resolve() / "poetry"
    return _check_review(poetry) if args.command == "review" else _check_poem(poetry, args.command)


if __name__ == "__main__":
    raise SystemExit(main())
