#!/usr/bin/env python3
"""fiction_writing tools, adapted from the Argus fiction_writing vertical (story_state patch engine,
anti-AI style lint, temporal check, novelty gate, review/revise completion check) and its shared
literary review contract.

  ids     print the allowed state_patch ops and the ids a patch may reference now
  apply   apply a state_patch to a story_state through the safe engine and write the result
  check   the deterministic gate on the prose, voice card and story_state (--stage review|revise)
  review  validate fiction/review.json and write fiction/revision_plan.json

Run from the project workspace. Exit 0: done / passes. Exit 1: the reason is printed, nothing is written.
Standard library only; if the optional opencc package is importable, the copy check also folds
traditional to simplified Chinese.
"""
from __future__ import annotations

import argparse
import copy
import functools
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

try:  # optional: fold traditional -> simplified before the verbatim comparison
    import opencc

    _T2S = opencc.OpenCC("t2s")
except Exception:  # absent: a wholly script-converted copy is not caught; NFKC still applies
    _T2S = None

SCHEMAS = Path(__file__).resolve().parent / "schemas"


class CheckError(ValueError):
    """An input that cannot pass: unreadable, malformed, or contradicting its contract."""


class PatchError(ValueError):
    """A state_patch that is invalid or cannot be safely applied."""


# --------------------------------------------------------------------------------------------------
# JSON-schema subset (type, enum, const, minLength, minimum, maximum, required, properties,
# additionalProperties, items, oneOf) -- all the bundled schemas use.
# --------------------------------------------------------------------------------------------------
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
}


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _selects(value: Any, branch: dict[str, Any]) -> bool:
    """True when ``branch`` is keyed by const properties (like ``op``) that ``value`` carries."""
    consts = {key: sub["const"] for key, sub in branch.get("properties", {}).items() if "const" in sub}
    return bool(consts) and isinstance(value, dict) and all(value.get(k) == c for k, c in consts.items())


def schema_errors(value: Any, schema: dict[str, Any], where: str = "$") -> list[str]:
    if "const" in schema and value != schema["const"]:
        return [f"{where}: {_short(value)} is not {schema['const']!r}"]
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(_TYPES[kind](value) for kind in kinds):
            return [f"{where}: {_short(value)} is not of type {' or '.join(kinds)}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{where}: {_short(value)} is not one of {schema['enum']}"]
    errors: list[str] = []
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where}: {_short(value)} is too short")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{where}: {value!r} is less than {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{where}: {value!r} is greater than {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        errors += [f"{where}: {key!r} is required" for key in schema.get("required", []) if key not in value]
        for key, item in value.items():
            if key in props:
                errors += schema_errors(item, props[key], f"{where}.{key}")
            elif extra is False:
                errors.append(f"{where}: {key!r} is not allowed")
            elif isinstance(extra, dict):
                errors += schema_errors(item, extra, f"{where}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += schema_errors(item, schema["items"], f"{where}[{i}]")
    if "oneOf" in schema:
        results = [schema_errors(value, branch, where) for branch in schema["oneOf"]]
        fits = sum(not result for result in results)
        if fits > 1:
            errors.append(f"{where}: fits more than one allowed form; exactly one is allowed")
        elif not fits:
            chosen = [result for result, branch in zip(results, schema["oneOf"]) if _selects(value, branch)]
            errors += chosen[0] if chosen else [" or ".join(e for result in results for e in result)]
    return errors


@functools.cache
def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def validate(value: Any, schema_name: str, label: str, error: type[ValueError] = CheckError) -> None:
    errors = schema_errors(value, _schema(schema_name))
    if errors:
        more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        raise error(f"invalid {label}: " + "; ".join(errors[:5]) + more)


def read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckError(f"{path} is not valid JSON: {exc}") from exc


def write_json(path: str | Path, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------------
# story_state + the safe state_patch engine. Guarantees: idempotent by patch_id; atomic (a bad op
# applies nothing); no op deletes prior state; every referenced id must exist; add_* never
# overwrites; timeline orders stay unique integers; the result is re-validated.
# --------------------------------------------------------------------------------------------------
def new_state(language: str = "zh", form: str = "fiction", title: str = "") -> dict[str, Any]:
    return {
        "meta": {"language": language, "form": form, "title": title, "revision": 0},
        "characters": {},
        "relationships": [],
        "world_rules": [],
        "locations": {},
        "items": {},
        "timeline": [],
        "open_threads": [],
        "foreshadowing": [],
        "chapter_summaries": [],
        "applied_patches": [],
    }


def validate_state(state: Any) -> None:
    validate(state, "story_state.schema.json", "story_state", PatchError)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise PatchError(msg)


def _op_set_meta(s: dict[str, Any], op: dict[str, Any]) -> None:
    allowed = {"form", "title", "language", "world_clock"}
    for key, val in (op.get("set") or {}).items():
        _require(key in allowed, f"set_meta: cannot set meta field {key!r}")
        s["meta"][key] = val


def _op_add_character(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    cid = op.get("id") or val.get("id")
    _require(bool(cid), "add_character: missing id")
    _require(cid not in s["characters"], f"add_character: id {cid!r} already exists (no overwrite)")
    _require(bool(val.get("name")), f"add_character: {cid!r} missing name")
    s["characters"][cid] = {
        "id": cid,
        "name": val["name"],
        "aliases": list(val.get("aliases", [])),
        "status": val.get("status", "alive"),
        "knows": list(val.get("knows", [])),
        "location": val.get("location"),
        "birth_year": val.get("birth_year"),
        "age": val.get("age"),
        "motivation": val.get("motivation", ""),
        "notes": val.get("notes", ""),
    }


def _op_update_character(s: dict[str, Any], op: dict[str, Any]) -> None:
    cid = op.get("id")
    _require(cid in s["characters"], f"update_character: unknown id {cid!r}")
    allowed = {"name", "aliases", "status", "knows", "location", "birth_year", "age", "motivation", "notes"}
    for key, val in (op.get("set") or {}).items():
        _require(key in allowed, f"update_character: cannot set {key!r}")
        s["characters"][cid][key] = val


def _op_add_relationship(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    frm, to = val.get("from"), val.get("to")
    _require(frm in s["characters"], f"add_relationship: unknown from {frm!r}")
    _require(to in s["characters"], f"add_relationship: unknown to {to!r}")
    _require(bool(val.get("type")), "add_relationship: missing type")
    s["relationships"].append({"from": frm, "to": to, "type": val["type"], "notes": val.get("notes", "")})


def _op_add_world_rule(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    rid = val.get("id")
    _require(bool(rid), "add_world_rule: missing id")
    _require(all(r["id"] != rid for r in s["world_rules"]), f"add_world_rule: id {rid!r} already exists")
    _require(bool(val.get("statement")), "add_world_rule: missing statement")
    s["world_rules"].append({"id": rid, "statement": val["statement"]})


def _op_add_location(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    lid = op.get("id") or val.get("id")
    _require(bool(lid), "add_location: missing id")
    _require(lid not in s["locations"], f"add_location: id {lid!r} already exists")
    _require(bool(val.get("name")), f"add_location: {lid!r} missing name")
    s["locations"][lid] = {"id": lid, "name": val["name"], "notes": val.get("notes", "")}


def _op_add_item(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    iid = op.get("id") or val.get("id")
    _require(bool(iid), "add_item: missing id")
    _require(iid not in s["items"], f"add_item: id {iid!r} already exists")
    _require(bool(val.get("name")), f"add_item: {iid!r} missing name")
    holder = val.get("holder")
    location = val.get("location")
    _require(holder is None or holder in s["characters"], f"add_item: unknown holder {holder!r}")
    _require(location is None or location in s["locations"], f"add_item: unknown location {location!r}")
    s["items"][iid] = {"id": iid, "name": val["name"], "holder": holder, "location": location,
                       "notes": val.get("notes", "")}


def _op_move_item(s: dict[str, Any], op: dict[str, Any]) -> None:
    iid = op.get("id")
    _require(iid in s["items"], f"move_item: unknown item {iid!r}")
    has_holder = "to_holder" in op
    _require(has_holder != ("to_location" in op), "move_item: provide exactly one of to_holder / to_location")
    if has_holder:
        holder = op.get("to_holder")
        _require(holder is None or holder in s["characters"], f"move_item: unknown holder {holder!r}")
        s["items"][iid]["holder"] = holder
        s["items"][iid]["location"] = None
    else:
        location = op.get("to_location")
        _require(location is None or location in s["locations"], f"move_item: unknown location {location!r}")
        s["items"][iid]["location"] = location
        s["items"][iid]["holder"] = None


def _op_add_timeline(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    tid = val.get("id")
    order = val.get("order")
    _require(bool(tid), "add_timeline: missing id")
    _require(isinstance(order, int), "add_timeline: order must be an integer")
    _require(all(t["id"] != tid for t in s["timeline"]), f"add_timeline: id {tid!r} already exists")
    _require(all(t["order"] != order for t in s["timeline"]),
             f"add_timeline: order {order} already used (timeline must stay ordered)")
    _require(bool(val.get("label")), "add_timeline: missing label")
    s["timeline"].append({"id": tid, "order": order, "label": val["label"],
                          "year": val.get("year"), "chapter": val.get("chapter")})
    s["timeline"].sort(key=lambda t: t["order"])


def _op_add_open_thread(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    tid = val.get("id")
    _require(bool(tid), "add_open_thread: missing id")
    _require(all(t["id"] != tid for t in s["open_threads"]), f"add_open_thread: id {tid!r} already exists")
    _require(bool(val.get("statement")), "add_open_thread: missing statement")
    s["open_threads"].append({"id": tid, "statement": val["statement"], "status": "open"})


def _op_resolve_thread(s: dict[str, Any], op: dict[str, Any]) -> None:
    tid = op.get("id")
    thread = next((t for t in s["open_threads"] if t["id"] == tid), None)
    _require(thread is not None, f"resolve_thread: unknown thread {tid!r}")
    thread["status"] = "resolved"


def _op_add_foreshadowing(s: dict[str, Any], op: dict[str, Any]) -> None:
    val = op.get("value") or {}
    fid = val.get("id")
    _require(bool(fid), "add_foreshadowing: missing id")
    _require(all(f["id"] != fid for f in s["foreshadowing"]), f"add_foreshadowing: id {fid!r} already exists")
    _require(bool(val.get("statement")), "add_foreshadowing: missing statement")
    s["foreshadowing"].append({
        "id": fid, "statement": val["statement"],
        "planted_chapter": val.get("planted_chapter"),
        "payoff_chapter": val.get("payoff_chapter"),
        "status": val.get("status", "planted"),
    })


def _op_resolve_foreshadowing(s: dict[str, Any], op: dict[str, Any]) -> None:
    fid = op.get("id")
    fore = next((f for f in s["foreshadowing"] if f["id"] == fid), None)
    _require(fore is not None, f"resolve_foreshadowing: unknown id {fid!r}")
    fore["status"] = "paid_off"
    fore["payoff_chapter"] = op.get("payoff_chapter", fore.get("payoff_chapter"))


def _op_add_chapter_summary(s: dict[str, Any], op: dict[str, Any]) -> None:
    chapter = op.get("chapter")
    _require(isinstance(chapter, int), "add_chapter_summary: chapter must be an integer")
    _require(all(c["chapter"] != chapter for c in s["chapter_summaries"]),
             f"add_chapter_summary: chapter {chapter} already summarized")
    s["chapter_summaries"].append({"chapter": chapter, "summary": op.get("summary", "")})


_HANDLERS = {
    "set_meta": _op_set_meta,
    "add_character": _op_add_character,
    "update_character": _op_update_character,
    "add_relationship": _op_add_relationship,
    "add_world_rule": _op_add_world_rule,
    "add_location": _op_add_location,
    "add_item": _op_add_item,
    "move_item": _op_move_item,
    "add_timeline": _op_add_timeline,
    "add_open_thread": _op_add_open_thread,
    "resolve_thread": _op_resolve_thread,
    "add_foreshadowing": _op_add_foreshadowing,
    "resolve_foreshadowing": _op_resolve_foreshadowing,
    "add_chapter_summary": _op_add_chapter_summary,
}

#: Required shape per op, shown to the writer before it drafts a patch.
_OP_SHAPES = {
    "set_meta": "set:{form?/title?/language?/world_clock?}",
    "add_character": "id, value:{name, aliases?, status?, knows?, location?, birth_year?, age?, motivation?, notes?}",
    "update_character": "id, set:{any of name/aliases/status/knows/location/birth_year/age/motivation/notes}",
    "add_relationship": "value:{from(char id), to(char id), type, notes?}",
    "add_world_rule": "value:{id, statement}",
    "add_location": "id, value:{name, notes?}",
    "add_item": "value:{id, name, holder?(char id), location?(loc id), notes?}",
    "move_item": "id, exactly one of to_holder(char id|null)/to_location(loc id|null)",
    "add_timeline": "value:{id, order(unique int), label, year?, chapter?}",
    "add_open_thread": "value:{id, statement}",
    "resolve_thread": "id(existing thread)",
    "add_foreshadowing": "value:{id, statement, planted_chapter?, payoff_chapter?, status?}",
    "resolve_foreshadowing": "id(existing), payoff_chapter?",
    "add_chapter_summary": "chapter(int), summary",
}

#: ops that accept the new id at EITHER the op top level OR value.id
_DUAL_ID_OPS = {"add_character", "add_location", "add_item"}


def normalize_ops(patch: Any) -> Any:
    """Decode an ``ops`` given as a JSON string (once); it must decode to an array."""
    if not isinstance(patch, dict) or not isinstance(patch.get("ops"), str):
        return patch
    try:
        parsed = json.loads(patch["ops"])
    except ValueError as exc:
        raise PatchError(f"ops is a string but not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise PatchError(f"ops decoded from a string is {type(parsed).__name__}, not an array")
    return {**patch, "ops": parsed}


def canonicalize_patch(patch: Any) -> Any:
    """Drop a ``value.id`` equal to the op-level id; conflicting ids are an error."""
    if not isinstance(patch, dict) or not isinstance(patch.get("ops"), list):
        return patch
    new_ops = []
    for idx, op in enumerate(patch["ops"]):
        val = op.get("value") if isinstance(op, dict) else None
        if (isinstance(op, dict) and op.get("op") in _DUAL_ID_OPS
                and isinstance(val, dict) and "id" in op and "id" in val):
            if op["id"] != val["id"]:
                raise PatchError(f"op[{idx}] ({op.get('op')}): conflicting ids — "
                                 f"op-level id {op['id']!r} != value.id {val['id']!r}")
            op = {**op, "value": {k: v for k, v in val.items() if k != "id"}}
        new_ops.append(op)
    return {**patch, "ops": new_ops}


def validate_patch(patch: Any) -> None:
    if isinstance(patch, dict) and isinstance(patch.get("ops"), list):
        for idx, op in enumerate(patch["ops"]):
            name = op.get("op") if isinstance(op, dict) else None
            if not (isinstance(name, str) and name in _HANDLERS):
                raise PatchError(f"op[{idx}]: unknown op {name!r} (allowed: {', '.join(_HANDLERS)})")
    validate(patch, "state_patch.schema.json", "state_patch", PatchError)


def apply_patch(state: dict[str, Any] | None, patch: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(new_state, result)``; ``state`` None starts a new story. The input is never mutated."""
    patch = canonicalize_patch(normalize_ops(patch))
    validate_patch(patch)
    if state is None:
        working = new_state(language=patch.get("language", "zh"))
    else:
        validate_state(state)
        working = copy.deepcopy(state)

    patch_id = patch["patch_id"]
    if patch_id in working["applied_patches"]:
        return working, {"applied": False, "patch_id": patch_id,
                         "revision": working["meta"]["revision"], "reason": "duplicate"}

    scratch = copy.deepcopy(working)
    for idx, op in enumerate(patch["ops"]):
        try:
            _HANDLERS[op["op"]](scratch, op)
        except PatchError as exc:
            raise PatchError(f"op[{idx}] ({op['op']}): {exc}") from exc
    scratch["meta"]["revision"] = working["meta"]["revision"] + 1
    scratch["applied_patches"].append(patch_id)
    validate_state(scratch)
    return scratch, {"applied": True, "patch_id": patch_id,
                     "revision": scratch["meta"]["revision"], "reason": "ok"}


def valid_reference_inventory(state: Any) -> dict[str, Any]:
    """The ids an op may reference now, per category (empty for a new story)."""
    s = state if isinstance(state, dict) else {}

    def named(key: str) -> dict[str, str]:
        section = s.get(key)
        return ({k: v.get("name", "") for k, v in section.items() if isinstance(v, dict)}
                if isinstance(section, dict) else {})

    def ids(key: str) -> list[Any]:
        section = s.get(key)
        return [e["id"] for e in section if isinstance(e, dict) and "id" in e] if isinstance(section, list) else []

    timeline = s.get("timeline") if isinstance(s.get("timeline"), list) else []
    return {
        "characters": named("characters"),
        "locations": named("locations"),
        "items": named("items"),
        "open_threads": ids("open_threads"),
        "foreshadowing": ids("foreshadowing"),
        "world_rules": ids("world_rules"),
        "timeline_orders": sorted(t["order"] for t in timeline
                                  if isinstance(t, dict) and isinstance(t.get("order"), int)),
    }


def generation_context(state: Any, language: str = "zh") -> str:
    """The allowed ops with their shapes and the ids a patch may reference now."""
    inv = valid_reference_inventory(state)
    zh = language != "en"
    lines = ["可用的 state_patch 操作(只能用这些 op):" if zh else "Allowed state_patch ops (use ONLY these):"]
    lines += [f"  - {op}: {_OP_SHAPES[op]}" for op in _HANDLERS]
    lines += ["", "当前可引用的 id(引用现有实体必须用下列 id;新实体请起一个未占用的新 id):" if zh
              else "Currently referenceable ids (reference existing entities by these; "
                   "give every NEW entity a fresh unused id):"]
    lines += [f"  characters: {inv['characters'] or '(none)'}",
              f"  locations:  {inv['locations'] or '(none)'}",
              f"  items:      {inv['items'] or '(none)'}",
              f"  open_threads:  {inv['open_threads'] or '(none)'}",
              f"  foreshadowing: {inv['foreshadowing'] or '(none)'}",
              f"  world_rules:   {inv['world_rules'] or '(none)'}",
              f"  used timeline orders: {inv['timeline_orders'] or '(none)'}", ""]
    lines.append(
        "硬规则:relationship.from/to、item.holder、move_item 目标必须是上面的 character/location id;"
        "add_* 不能覆盖已存在 id;timeline.order 为未用过的整数;没有删除 op。"
        if zh else
        "Hard rules: relationship.from/to, item.holder, move_item targets MUST be ids listed above; "
        "add_* may not overwrite an existing id; timeline.order is an unused integer; there is no delete op.")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------
# Voice card (style_profile): only forbidden_lexicon is a hard word-level contract.
# --------------------------------------------------------------------------------------------------
def forbidden_lexicon(card: dict[str, Any]) -> list[str]:
    return [w for w in (card.get("forbidden_lexicon") or []) if w]


def avoided_terms(card: dict[str, Any]) -> list[str]:
    return [w for w in ((card.get("lexicon") or {}).get("avoided_terms") or []) if w]


def novelty_budget(card: dict[str, Any]) -> dict[str, Any]:
    """Declared anti-copy thresholds: max_verbatim_run (positive int), max_overlap_ratio (>= 0)."""
    nb = card.get("novelty_budget") or {}
    out: dict[str, Any] = {}
    run = nb.get("max_verbatim_run")
    if isinstance(run, int) and not isinstance(run, bool) and run > 0:
        out["max_verbatim_run"] = run
    ratio = nb.get("max_overlap_ratio")
    if isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and ratio >= 0:
        out["max_overlap_ratio"] = float(ratio)
    return out


# --------------------------------------------------------------------------------------------------
# Anti-AI style lint. The cliché tables are model-seed (pending BCC / COCA calibration): a hit is a
# NON-blocking ai_tell cue for the reviewer. Only a declared forbidden_lexicon term blocks.
# --------------------------------------------------------------------------------------------------
_CALIBRATION = "model-seed (BCC-pending)"

_ZH_FULLTEXT: dict[str, list[re.Pattern[str]]] = {
    "抽象抒情直说": [re.compile(r"思念|孤独|悲伤|温暖|治愈")],
    "排比堆砌": [re.compile(r"(?:[^，。！？\n]{1,20}的[^，。！？\n]{1,20}，){3,}")],
    "万能陈词": [re.compile(
        r"仿佛全世界|像被抽空|五味杂陈|潸然泪下|嘴角[勾扬]起.{0,4}弧度|不禁潸然")],
    "翻译腔欧化": [re.compile(
        r"进行了一[次场]|做出了.{0,6}的动作|其中的一个|不得不说|一个.{0,8}的存在")],
    "情绪涌动模板": [re.compile(
        r"(?:心[中里底头]|心底|胸口|眼[眶底]|脑海|喉[咙间])(?:深处)?[，、]?[^，。！？\n]{0,4}"
        r"(?:涌|泛|升|漫|溢|袭|漾)(?:起|上|来|过)[^，。！？\n]{0,6}"
        r"(?:暖流|酸楚|暖意|悸动|情绪|思绪|温暖|甜蜜|苦涩|愧疚|寒意|感动|一丝|一股|一阵|一抹)")],
    "凝固时刻": [re.compile(
        r"(?:空气|时间|时光|一切|周围|四周|世界|画面)[^，。！？\n]{0,3}"
        r"(?:仿佛|似乎|像是|好像|竟)?[^，。！？\n]{0,2}(?:凝固|静止|停滞|凝滞)")],
    "时刻拔高": [re.compile(r"(?:在)?(?:这一|那一)(?:刻|瞬间|刹那)|刹那间|一瞬间")],
    "虚化感受": [re.compile(r"说不出的|难以言喻|难以名状|无法形容|一种[^，。！？\n]{0,8}的感觉")],
    "副词堆砌": [re.compile(
        r"(?:(?:无声|静静|轻轻|缓缓|默默|淡淡|悄悄|微微|深深)地[^。！？\n]{0,12}){2,}")],
}
_ZH_PARA_INITIAL: dict[str, list[re.Pattern[str]]] = {
    "廉价转折词": [re.compile(r"^(然而|但是|其实|事实上)")],
}
_ZH_ENDING: dict[str, list[re.Pattern[str]]] = {
    "升华式结尾": [re.compile(
        r"愿[^。！\n]{0,20}[。！]|让我们|在这个.{0,12}的时代|"
        r"这就是.{0,15}的意义|无论.{0,20}都(?:是|会|能|要)")],
}
_EN_FULLTEXT: dict[str, list[re.Pattern[str]]] = {
    "filter_words": [re.compile(r"\b(felt|saw|noticed|realized|watched) that\b", re.I)],
    "telling_emotion": [re.compile(r"\b(sadness|loneliness|joy|warmth|happiness)\b", re.I)],
    "adverb_tags": [re.compile(r"\bsaid\s+\w+ly\b", re.I)],
    "purple_cliche": [re.compile(
        r"a shiver ran down|time seemed to stand still|a single tear|"
        r"heart skipped a beat", re.I)],
    "frozen_moment": [re.compile(
        r"the air (?:seemed to |)(?:freeze|thicken|grew still)|"
        r"the world (?:held its breath|seemed to stop|stood still)", re.I)],
    "vague_feeling": [re.compile(
        r"an? (?:odd|strange|inexplicable|unfamiliar|nameless|quiet) "
        r"(?:sense|feeling|sensation)|couldn'?t (?:quite )?(?:place|name|explain|shake)|"
        r"something (?:unspoken|unsaid|passed between)", re.I)],
}
_EN_PARA_INITIAL: dict[str, list[re.Pattern[str]]] = {
    "throat_clearing": [re.compile(r"^(However|Indeed|In fact|Honestly),", re.I)],
}
_EN_ENDING: dict[str, list[re.Pattern[str]]] = {
    "uplift_ending": [re.compile(
        r"In the end,|Little did (she|he|they) know|a testament to", re.I)],
}


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _style_finding(ftype: str, cliche_class: str, blocking: bool, detail: str,
                   line: int | None = None) -> dict[str, Any]:
    return {"type": ftype, "cliche_class": cliche_class, "severity": "major" if blocking else "note",
            "blocking": blocking, "line": line, "detail": detail, "calibration": _CALIBRATION}


def _paragraphs(text: str) -> list[tuple[str, int]]:
    """``(paragraph_text, start_line)`` for each blank-line-separated block."""
    out: list[tuple[str, int]] = []
    idx = 0
    for part in re.split(r"(\n[ \t]*\n)", text):
        if part.strip() and not re.fullmatch(r"\n[ \t]*\n", part):
            out.append((part, _line_of(text, idx)))
        idx += len(part)
    return out


def check_style(text: str, card: dict[str, Any] | None = None, language: str = "zh") -> list[dict[str, Any]]:
    card = card or {}
    findings: list[dict[str, Any]] = []
    if language == "en":
        fulltext, para_initial, ending = _EN_FULLTEXT, _EN_PARA_INITIAL, _EN_ENDING
    else:
        fulltext, para_initial, ending = _ZH_FULLTEXT, _ZH_PARA_INITIAL, _ZH_ENDING

    for cls, pats in fulltext.items():
        for pat in pats:
            for m in pat.finditer(text):
                findings.append(_style_finding(
                    "ai_tell", cls, False, m.group(0).strip()[:50], _line_of(text, m.start())))

    paras = _paragraphs(text)
    for cls, pats in para_initial.items():
        for para_text, line in paras:
            head = para_text.lstrip()
            for pat in pats:
                if pat.search(head):
                    findings.append(_style_finding("ai_tell", cls, False, head[:24].strip(), line))

    if paras:  # slogan / uplift ending: only the final paragraph
        last_text, last_line = paras[-1]
        for cls, pats in ending.items():
            for pat in pats:
                m = pat.search(last_text)
                if m:
                    findings.append(_style_finding("ai_tell", cls, False, m.group(0).strip()[:50], last_line))

    for w in forbidden_lexicon(card):
        idx = text.find(w)
        if idx != -1:
            findings.append(_style_finding("voice", "forbidden_lexicon", True,
                                           f"forbidden term {w!r} present", _line_of(text, idx)))
    for w in avoided_terms(card):
        idx = text.find(w)
        if idx != -1:
            findings.append(_style_finding("voice", "avoided_term", False,
                                           f"avoided term {w!r} present", _line_of(text, idx)))
    return findings


# --------------------------------------------------------------------------------------------------
# Temporal / age consistency over story_state (blocking; silent when the numbers are absent).
# --------------------------------------------------------------------------------------------------
def _temporal_finding(detail: str, character_id: str | None = None) -> dict[str, Any]:
    return {"type": "temporal_consistency", "severity": "major", "blocking": True,
            "character_id": character_id, "detail": detail}


def check_temporal_consistency(state: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    clock = (state.get("meta") or {}).get("world_clock") or {}
    current_year = clock.get("current_year")

    for cid, char in (state.get("characters") or {}).items():
        if not isinstance(char, dict):
            continue
        name = char.get("name", cid)
        age = char.get("age")
        birth = char.get("birth_year")
        if isinstance(age, int) and age < 0:
            findings.append(_temporal_finding(f"{name}: age {age} is negative", cid))
        if isinstance(birth, int) and isinstance(current_year, int) and birth > current_year:
            findings.append(_temporal_finding(
                f"{name}: birth_year {birth} is after the story's current_year "
                f"{current_year} (born in the future)", cid))
        if isinstance(age, int) and isinstance(birth, int) and isinstance(current_year, int):
            expected = current_year - birth
            if expected != age:
                findings.append(_temporal_finding(
                    f"{name}: stated age {age} contradicts current_year {current_year} "
                    f"− birth_year {birth} = {expected}", cid))

    dated = [t for t in (state.get("timeline") or [])
             if isinstance(t, dict) and isinstance(t.get("order"), int) and isinstance(t.get("year"), int)]
    dated.sort(key=lambda t: t["order"])
    for earlier, later in zip(dated, dated[1:]):
        if later["year"] < earlier["year"]:
            findings.append(_temporal_finding(
                f"timeline: {later.get('id')!r} (order {later['order']}, year "
                f"{later['year']}) comes after {earlier.get('id')!r} (order "
                f"{earlier['order']}, year {earlier['year']}) but carries an earlier year"))
    return findings


# --------------------------------------------------------------------------------------------------
# Novelty ('不能抄'): verbatim overlap of the prose with fiction/reference_text.md. A long shared run is
# a fact, so it blocks; thresholds are model-seed and set high; paraphrase is left to the reviewer.
# --------------------------------------------------------------------------------------------------
_DEFAULTS = {"zh": {"note_run": 12, "block_run": 24}, "en": {"note_run": 6, "block_run": 12}}
_RATIO_NOTE_FLOOR = 0.05
_DEFAULT_OVERLAP_BLOCK = 0.5
_MIN_COVERED_FOR_RATIO_BLOCK = 40


def _fold_token(token: str, language: str) -> str:
    token = unicodedata.normalize("NFKC", token)
    if language != "en" and _T2S is not None:
        token = _T2S.convert(token)
    return token


def _tokens(text: str, language: str) -> tuple[list[str], list[int]]:
    """zh: each letter/ideograph/digit (punctuation and spaces dropped); en: each lowercased word."""
    tokens: list[str] = []
    idx: list[int] = []
    if language == "en":
        for m in re.finditer(r"[A-Za-z0-9']+", text):
            tokens.append(_fold_token(m.group(0).lower(), language))
            idx.append(m.start())
    else:
        for i, ch in enumerate(text):
            if unicodedata.category(ch)[0] in ("L", "N"):
                tokens.append(_fold_token(ch, language))
                idx.append(i)
    return tokens, idx


def _verbatim_runs(draft: list[str], ref: list[str], k: int) -> list[tuple[int, int]]:
    """Maximal, non-overlapping ``(draft_start, length)`` runs of >= ``k`` shared tokens."""
    if k <= 0 or len(draft) < k or len(ref) < k:
        return []
    shingles: dict[tuple[str, ...], list[int]] = {}
    for i in range(len(ref) - k + 1):
        shingles.setdefault(tuple(ref[i:i + k]), []).append(i)

    def extend(di: int, ri: int) -> int:
        n = 0
        while di + n < len(draft) and ri + n < len(ref) and draft[di + n] == ref[ri + n]:
            n += 1
        return n

    runs: list[tuple[int, int]] = []
    i = 0
    while i <= len(draft) - k:
        starts = shingles.get(tuple(draft[i:i + k]))
        if not starts:
            i += 1
            continue
        best = max(extend(i, ri) for ri in starts)
        runs.append((i, best))
        i += best
    return runs


def check_novelty(draft_text: str, reference_text: str, card: dict[str, Any] | None = None,
                  language: str = "zh") -> list[dict[str, Any]]:
    card = card or {}
    if not reference_text.strip() or not draft_text.strip():
        return []
    lang = "en" if language == "en" else "zh"
    defaults = _DEFAULTS[lang]
    budget = novelty_budget(card)
    block_run = int(budget.get("max_verbatim_run") or defaults["block_run"])
    note_run = min(defaults["note_run"], block_run)
    max_ratio = budget.get("max_overlap_ratio")
    unit = "char" if lang == "zh" else "word"
    join = "".join if lang == "zh" else " ".join

    d_tokens, d_idx = _tokens(draft_text, lang)
    r_tokens, _ = _tokens(reference_text, lang)
    findings: list[dict[str, Any]] = []
    covered = 0
    for start, length in _verbatim_runs(d_tokens, r_tokens, note_run):
        covered += length
        blocking = length >= block_run
        snippet = join(d_tokens[start:start + length])
        findings.append({
            "type": "verbatim_copy", "severity": "major" if blocking else "note", "blocking": blocking,
            "line": draft_text.count("\n", 0, d_idx[start]) + 1, "run_len": length,
            "detail": (f"{length}-{unit} verbatim run copied from the reference: {snippet[:60]!r}"
                       + ("" if blocking else " (below block threshold)")),
            "calibration": _CALIBRATION,
        })

    if d_tokens:
        ratio = covered / len(d_tokens)
        if max_ratio is not None:
            blocks_ratio = ratio > float(max_ratio)
            thr = f"declared novelty_budget.max_overlap_ratio {max_ratio}"
        else:
            blocks_ratio = ratio > _DEFAULT_OVERLAP_BLOCK and covered >= _MIN_COVERED_FOR_RATIO_BLOCK
            thr = f"model-seed default {_DEFAULT_OVERLAP_BLOCK}"
        if blocks_ratio:
            findings.append({
                "type": "verbatim_copy", "severity": "major", "blocking": True, "line": None, "run_len": None,
                "detail": f"verbatim overlap ratio {ratio:.2f} ({covered} tokens) exceeds {thr}",
                "calibration": _CALIBRATION,
            })
        elif ratio > _RATIO_NOTE_FLOOR:
            findings.append({
                "type": "verbatim_copy", "severity": "note", "blocking": False, "line": None, "run_len": None,
                "detail": (f"verbatim overlap ratio {ratio:.2f} of the draft matches the reference (note; "
                           "declare novelty_budget.max_overlap_ratio to make this blocking)"),
                "calibration": _CALIBRATION,
            })
    return findings


# --------------------------------------------------------------------------------------------------
# The review / revise completion check.
# --------------------------------------------------------------------------------------------------
def stage_findings(stage: str, project_root: Path) -> list[dict[str, Any]]:
    fiction = project_root / "fiction"
    prose_name = "draft.md" if stage == "review" else "final.md"
    state_name = "story_state.json" if stage == "review" else "updated_story_state.json"
    prose = (fiction / prose_name).read_text(encoding="utf-8")
    if not prose.strip():
        raise CheckError(f"{prose_name} is empty")
    card = read_json(fiction / "style_profile.json")
    brief = read_json(fiction / "creative_brief.json")
    state = read_json(fiction / state_name)
    if not isinstance(brief, dict):
        raise CheckError("creative_brief.json must be an object")
    validate(card, "style_profile.schema.json", "style_profile")
    validate(state, "story_state.schema.json", state_name)
    language = (card.get("meta") or {}).get("language") or brief.get("language") or "zh"
    findings = check_style(prose, card, language)
    findings += check_temporal_consistency(state)
    reference = fiction / "reference_text.md"
    if reference.is_file():
        findings += check_novelty(prose, reference.read_text(encoding="utf-8"), card, language)
    return findings


# --------------------------------------------------------------------------------------------------
# The literary review contract with the fiction finding vocabulary.
# --------------------------------------------------------------------------------------------------
#: Continuity types: hard contradictions (temporal_consistency and verbatim_copy are machine-provable).
CONTINUITY_TYPES = frozenset({
    "status", "knowledge", "item_location", "co_location", "timeline", "world_rule", "motivation",
    "foreshadowing", "viewpoint", "language", "temporal_consistency", "verbatim_copy",
})
#: Craft types: heuristic observations (voice still blocks on a forbidden_lexicon term).
CRAFT_TYPES = frozenset({
    "style", "voice", "concreteness", "show_tell", "over_summary", "mechanical_twist", "pacing", "ending",
    "ai_tell",
})
FINDING_TYPES = CONTINUITY_TYPES | CRAFT_TYPES
_SEV_RANK = {s: i for i, s in enumerate(("critical", "major", "minor", "note"))}


def normalize_review(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CheckError("review must be a JSON object")
    review = dict(raw)
    review.setdefault("findings", [])
    if not isinstance(review["findings"], list):
        raise CheckError("review.findings must be an array")
    findings = []
    for f in review["findings"]:
        if not isinstance(f, dict):
            raise CheckError("each finding must be an object")
        g = dict(f)
        if isinstance(g.get("id"), (int, float)) and not isinstance(g.get("id"), bool):
            g["id"] = str(g["id"])  # models often number findings 1, 2, ...
        g.setdefault("must_not_break", [])
        g.setdefault("violated_constraint", "")
        findings.append(g)
    review["findings"] = findings
    validate(review, "review.schema.json", "review")
    if any(f["blocking"] for f in findings) and review["verdict"] != "revise":
        raise CheckError("a blocking finding stands but verdict is not 'revise'")
    if not findings and review["verdict"] != "done":
        raise CheckError("no findings but verdict is not 'done'")
    for f in findings:
        if f["type"] not in FINDING_TYPES:
            raise CheckError(f"finding {f['id']!r}: unknown type {f['type']!r} "
                             f"(vocabulary: {', '.join(sorted(FINDING_TYPES))})")
    return review


def revision_plan(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Blocking findings first, then by severity; each keeps its must_not_break invariants."""
    ordered = sorted(review["findings"], key=lambda f: (not f["blocking"], _SEV_RANK.get(f["severity"], 99)))
    return [{"finding_id": f["id"], "type": f["type"], "severity": f["severity"], "blocking": f["blocking"],
             "location": f["location"], "suggested_action": f["suggested_action"],
             "must_not_break": list(f["must_not_break"])} for f in ordered]


# --------------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------------
def cmd_ids(args: argparse.Namespace) -> int:
    try:
        state = read_json(args.state) if args.state else None
    except (OSError, ValueError) as exc:
        print(f"cannot read the state: {exc}", file=sys.stderr)
        return 1
    meta = state.get("meta") if isinstance(state, dict) else None
    language = args.language or (meta if isinstance(meta, dict) else {}).get("language") or "zh"
    print(generation_context(state, language))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    try:
        state = read_json(args.state) if args.state else None
        patch = read_json(args.patch)
    except (OSError, ValueError) as exc:
        print(f"cannot read the input: {exc}", file=sys.stderr)
        return 1
    try:
        new, result = apply_patch(state, patch)
    except PatchError as exc:
        language = patch.get("language") if isinstance(patch, dict) else None
        print(f"rejected, nothing written: {exc}\n", file=sys.stderr)
        print(generation_context(state, language or "zh"), file=sys.stderr)
        return 1
    write_json(args.out, new)
    done = "applied" if result["applied"] else "was already applied; state unchanged,"
    print(f"{result['patch_id']} {done} revision {result['revision']} written to {args.out}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        findings = stage_findings(args.stage, Path(args.project_root))
    except (OSError, ValueError) as exc:
        print(f"{args.stage} check: inputs invalid: {exc}", file=sys.stderr)
        return 1
    blocking = sum(1 for f in findings if f["blocking"])
    for f in sorted(findings, key=lambda f: not f["blocking"]):
        kind = f["type"] + (f"/{f['cliche_class']}" if f.get("cliche_class") else "")
        where = f" (line {f['line']})" if f.get("line") else ""
        print(f"{'BLOCKING' if f['blocking'] else 'note'} {kind}{where}: {f['detail']}")
    print(f"{args.stage} check: {blocking} blocking, {len(findings) - blocking} notes")
    return 1 if blocking else 0


def cmd_review(args: argparse.Namespace) -> int:
    fiction = Path(args.project_root) / "fiction"
    try:
        review = normalize_review(read_json(fiction / "review.json"))
    except (OSError, ValueError) as exc:
        print(f"review.json rejected, nothing written: {exc}", file=sys.stderr)
        return 1
    plan = revision_plan(review)
    write_json(fiction / "revision_plan.json", plan)
    blocking = sum(1 for p in plan if p["blocking"])
    print(f"verdict {review['verdict']}: {len(plan)} findings, {blocking} blocking; "
          f"wrote {fiction / 'revision_plan.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    ids = sub.add_parser("ids", help="print the allowed ops and the ids a patch may reference")
    ids.add_argument("--state", help="current story_state.json (omit for a new story)")
    ids.add_argument("--language", choices=("zh", "en"), help="default: the state's language, else zh")
    ids.set_defaults(run=cmd_ids)
    apply = sub.add_parser("apply", help="apply a state_patch through the safe engine")
    apply.add_argument("--state", help="current story_state.json (omit for the first patch of a new story)")
    apply.add_argument("--patch", required=True, help="state_patch.json")
    apply.add_argument("--out", required=True, help="where to write the new story_state (may equal --state)")
    apply.set_defaults(run=cmd_apply)
    check = sub.add_parser("check", help="blocking checks on the prose, voice card and story_state")
    check.add_argument("--project-root", default=".")
    check.add_argument("--stage", required=True, choices=("review", "revise"),
                       help="review: draft.md + story_state.json; revise: final.md + updated_story_state.json")
    check.set_defaults(run=cmd_check)
    review = sub.add_parser("review", help="validate fiction/review.json, write fiction/revision_plan.json")
    review.add_argument("--project-root", default=".")
    review.set_defaults(run=cmd_review)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
