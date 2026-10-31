"""Standalone checks for the prose pack: task envelope, prose structure, review.

brief      prose/task_envelope.json -> prose/prose_brief.json
structure  prose/prose_state.json + prose/draft.md (or --final: prose/final.md) -> prose/structure_report.json
review     prose/review.json -> prose/revision_plan.json

Run from the project workspace or pass --project-root. Exit 0: the input passes. Exit 1: each issue is
printed and, except for structure, which always rewrites its report, nothing is written.
These are thin structural checks; they never judge whether the prose is good.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMAS = Path(__file__).resolve().parent / "schemas"

#: The fields a prose_state must declare (the piece's private craft plan).
PROSE_STATE_FIELDS: tuple[str, ...] = (
    "narrative_center", "observation_subject", "factual_anchors",
    "memory_boundary", "paragraph_movement", "ending_strategy",
)

#: Machine-decidable prose finding types (structure + hard constraints only).
STRUCTURE_FINDING_TYPES: frozenset[str] = frozenset({
    "structure", "language", "paragraph_count", "banned_word", "empty",
})
#: Live-reviewer craft types: NON-blocking, never mechanized.
PROSE_CRAFT_TYPES: frozenset[str] = frozenset({
    "observation", "fact_memory", "fabrication", "movement", "imagery",
    "ending", "template",
})
PROSE_FINDING_TYPES: frozenset[str] = STRUCTURE_FINDING_TYPES | PROSE_CRAFT_TYPES

#: Prose forms this pack handles (zh names + english aliases).
PROSE_FORMS: frozenset[str] = frozenset({
    "lyric_essay", "narrative_essay", "essay", "memoir",
    "散文", "抒情散文", "叙事散文", "随笔", "回忆",
})

#: Modes that operate ON an existing text and therefore REQUIRE a source ref.
_SOURCE_REQUIRING_MODES = frozenset({"continuation", "rewrite", "expand", "polish", "proofread", "critique"})
_SOURCE_ROLES = frozenset({"source_text", "prior_state"})
_ENVELOPE_DEFAULTS: dict[str, Any] = {
    "genre_profile": "", "audience": "", "target_length": None, "constraints": [],
    "reference_inputs": [], "retrieval_policy": "none", "output_requirements": {},
}
_STRIP_FIELDS = ("task_id", "mode", "language", "form", "genre_profile", "intent", "audience", "retrieval_policy")

#: Importance order used to rank the revision plan within each blocking class.
_SEV_RANK = {s: i for i, s in enumerate(("critical", "major", "minor", "note"))}


class CheckError(ValueError):
    """An input that cannot pass: malformed, incomplete, or contradicting its contract."""


# --- the subset of JSON Schema draft-07 the bundled schemas use -------------------------------------

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
}


def schema_errors(value: Any, schema: dict[str, Any], where: str = "$") -> list[str]:
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(_TYPES[kind](value) for kind in kinds):
            return [f"{where}: {value!r} is not of type {' or '.join(kinds)}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{where}: {value!r} is not one of {schema['enum']}"]
    errors: list[str] = []
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where}: {value!r} is too short")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{where}: {value!r} is less than the minimum of {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{where}: {value!r} is greater than the maximum of {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [f"{where}: {key!r} is a required property" for key in schema.get("required", []) if key not in value]
        if schema.get("additionalProperties") is False:
            errors += [f"{where}: additional property {key!r} is not allowed" for key in value if key not in props]
        for key, sub in props.items():
            if key in value:
                errors += schema_errors(value[key], sub, f"{where}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += schema_errors(item, schema["items"], f"{where}[{i}]")
    return errors


def validate(value: Any, schema_name: str, label: str) -> None:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    errors = schema_errors(value, schema)
    if errors:
        raise CheckError(f"invalid {label}: " + "; ".join(errors))


# --- intake: task envelope -> prose brief ------------------------------------------------------------

def normalize_envelope(raw: Any) -> dict[str, Any]:
    """Fill documented defaults, strip string fields, validate, then enforce the source rule."""
    if not isinstance(raw, dict):
        raise CheckError("task_envelope must be a JSON object")
    env = dict(raw)
    for key, default in _ENVELOPE_DEFAULTS.items():
        env.setdefault(key, default)
    for key in _STRIP_FIELDS:
        if isinstance(env.get(key), str):
            env[key] = env[key].strip()
    validate(env, "task_envelope.schema.json", "task_envelope")
    if env["mode"] in _SOURCE_REQUIRING_MODES:
        roles = {r.get("role") for r in env["reference_inputs"]}
        if not (roles & _SOURCE_ROLES):
            raise CheckError(
                f"mode={env['mode']!r} operates on existing text but no reference_inputs "
                f"with role in {sorted(_SOURCE_ROLES)} was provided"
            )
    return env


def brief_from_envelope(raw: Any) -> dict[str, Any]:
    env = normalize_envelope(raw)
    if env["form"] not in PROSE_FORMS:
        raise CheckError(f"prose does not handle form {env['form']!r} (expected one of {sorted(PROSE_FORMS)})")
    out_req = env.get("output_requirements") or {}
    spec = {
        "language": env["language"],
        "min_paragraphs": out_req.get("min_paragraphs"),
        "max_paragraphs": out_req.get("max_paragraphs"),
        "banned_words": list(out_req.get("banned_words", [])),
    }
    return {
        "task_id": env["task_id"],
        "language": env["language"],
        "form": env["form"],
        "mode": env["mode"],
        "intent": env["intent"],
        "spec": {k: v for k, v in spec.items() if v not in (None, [])},
        "constraints": list(env.get("constraints", [])),
        "reference_inputs": list(env.get("reference_inputs", [])),
    }


# --- structure: prose_state completeness + declared hard constraints ---------------------------------

def _finding(ftype: str, detail: str, where: str | None = None) -> dict[str, Any]:
    return {"type": ftype, "severity": "blocking", "location": where, "detail": detail}


def validate_prose_state(state: Any) -> list[dict[str, Any]]:
    """Return blocking findings for any required prose_state field missing/empty."""
    if not isinstance(state, dict):
        raise CheckError("prose_state must be an object")
    findings: list[dict[str, Any]] = []
    for field in PROSE_STATE_FIELDS:
        val = state.get(field)
        if val is None or (isinstance(val, (str, list, dict)) and len(val) == 0):
            findings.append(_finding("structure", f"prose_state missing {field!r}", field))
    return findings


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _han_ratio(s: str) -> float:
    non_ws = [c for c in s if not c.isspace()]
    if not non_ws:
        return 0.0
    han = sum(1 for c in non_ws if "一" <= c <= "鿿")
    return han / len(non_ws)


def check_draft(text: str, spec: Any = None) -> list[dict[str, Any]]:
    """Blocking findings where ``text`` violates ``spec`` (all keys optional):
    ``language`` ('zh'|'en'), ``min_paragraphs``, ``max_paragraphs`` (int), ``banned_words`` (list[str])."""
    spec = spec or {}
    if not isinstance(spec, dict):
        raise CheckError("prose spec must be an object")
    findings: list[dict[str, Any]] = []
    paras = _paragraphs(text)
    if not paras:
        return [_finding("empty", "draft is empty (no paragraphs)")]
    if spec.get("min_paragraphs") is not None and len(paras) < int(spec["min_paragraphs"]):
        findings.append(_finding("paragraph_count", f"{len(paras)} paragraphs, below min {spec['min_paragraphs']}"))
    if spec.get("max_paragraphs") is not None and len(paras) > int(spec["max_paragraphs"]):
        findings.append(_finding("paragraph_count", f"{len(paras)} paragraphs, above max {spec['max_paragraphs']}"))
    lang = spec.get("language")
    if lang == "zh" and _han_ratio(text) < 0.5:
        findings.append(_finding("language", "declared zh but not predominantly Han script"))
    if lang == "en" and _han_ratio(text) > 0.2:
        findings.append(_finding("language", "declared en but contains substantial Han script"))
    for w in (spec.get("banned_words") or []):
        if w and w in text:
            findings.append(_finding("banned_word", f"banned cliché {w!r} present"))
    return findings


def structure_findings(prose: Path, name: str) -> list[dict[str, Any]]:
    try:
        text = (prose / name).read_text(encoding="utf-8")
        state = json.loads((prose / "prose_state.json").read_text(encoding="utf-8"))
        return validate_prose_state(state) + check_draft(text, state.get("spec"))
    except (OSError, ValueError, TypeError) as exc:
        return [_finding("structure", f"prose structure inputs invalid: {exc}")]


# --- review -> revision plan -------------------------------------------------------------------------

def normalize_review(raw: Any) -> dict[str, Any]:
    """Fill per-finding defaults, then check the schema, the prose vocabulary and verdict coherence."""
    if not isinstance(raw, dict):
        raise CheckError("review must be a JSON object")
    review = dict(raw)
    review.setdefault("findings", [])
    if not isinstance(review["findings"], list):
        raise CheckError("review.findings must be an array")
    norm: list[dict[str, Any]] = []
    for f in review["findings"]:
        if not isinstance(f, dict):
            raise CheckError("each finding must be an object")
        g = dict(f)
        # An integer finding id (1, 2, ...) is coerced rather than rejecting an otherwise valid review.
        if isinstance(g.get("id"), (int, float)) and not isinstance(g.get("id"), bool):
            g["id"] = str(g["id"])
        g.setdefault("must_not_break", [])
        g.setdefault("violated_constraint", "")
        norm.append(g)
    review["findings"] = norm
    validate(review, "review.schema.json", "review")
    findings = review["findings"]
    if any(f["blocking"] for f in findings) and review["verdict"] != "revise":
        raise CheckError("a blocking finding stands but verdict is not 'revise' — a blocking finding "
                         "can never coexist with a review that declares the work done")
    if not findings and review["verdict"] != "done":
        raise CheckError("no findings but verdict is not 'done' — cannot request a revision with nothing to act on")
    for f in findings:
        if f["type"] not in PROSE_FINDING_TYPES:
            raise CheckError(f"finding {f['id']!r}: unknown type {f['type']!r} (vocabulary: {sorted(PROSE_FINDING_TYPES)})")
    return review


def revision_plan(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Blocking findings first, then by descending severity, each with its must_not_break invariants."""
    ordered = sorted(review["findings"], key=lambda f: (not f["blocking"], _SEV_RANK.get(f["severity"], 99)))
    return [
        {
            "finding_id": f["id"], "type": f["type"], "severity": f["severity"], "blocking": f["blocking"],
            "location": f["location"], "suggested_action": f["suggested_action"],
            "must_not_break": list(f.get("must_not_break", [])),
        }
        for f in ordered
    ]


# --- command line ------------------------------------------------------------------------------------

def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CheckError(f"missing {path}") from None
    except (OSError, ValueError) as exc:
        raise CheckError(f"{path} is not valid JSON: {exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     epilog="\n".join(__doc__.splitlines()[2:]),
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("brief", "check the task envelope and write the brief"),
                       ("structure", "check prose_state and the text, write structure_report.json"),
                       ("review", "check review.json and write revision_plan.json")):
        command = commands.add_parser(name, help=text, description=text)
        command.add_argument("--project-root", default=".", help="project workspace holding prose/ (default: .)")
        if name == "structure":
            command.add_argument("--final", action="store_true", help="check prose/final.md instead of prose/draft.md")
    args = parser.parse_args(argv)
    prose = Path(args.project_root) / "prose"
    try:
        if args.command == "brief":
            _write(prose / "prose_brief.json", brief_from_envelope(_read(prose / "task_envelope.json")))
            print(f"ok: wrote {prose / 'prose_brief.json'}")
        elif args.command == "review":
            plan = revision_plan(normalize_review(_read(prose / "review.json")))
            _write(prose / "revision_plan.json", plan)
            print(f"ok: wrote {prose / 'revision_plan.json'} ({len(plan)} instructions, "
                  f"{sum(p['blocking'] for p in plan)} blocking)")
        else:
            name = "final.md" if args.final else "draft.md"
            findings = structure_findings(prose, name)
            _write(prose / "structure_report.json", {"text": f"prose/{name}", "findings": findings})
            for finding in findings:
                print(f"{finding['type']}: {finding['detail']}")
            if findings:
                return 1
            print(f"ok: prose/{name} has no structure findings; wrote {prose / 'structure_report.json'}")
    except CheckError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
