"""Run and interpret actual KiCad 9 commands; no project input is rewritten."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError

from .design import text


def environment(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("KICAD")}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "xdg"), KICAD_CONFIG_HOME=str(home / "kicad"), LC_ALL="C.UTF-8")
    return env


def version() -> str:
    try:
        result = subprocess.run(["kicad-cli", "version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"KiCad 9 CLI is required: {exc}") from exc
    value = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"9\.\d+\.\d+", value):
        raise EvidenceError(f"expected KiCad 9.x.y, received {value!r}: {result.stderr}")
    return value


def steps(plan: dict, output: Path) -> list[tuple[str, list[str]]]:
    result = []
    design = plan["design"]
    for check in plan.get("checks", []):
        kind = check["kind"]
        arguments = ["kicad-cli", "sch" if kind == "erc" else "pcb", kind,
                     "--format", "json", "--units", "mm", "--severity-all", "--exit-code-violations"]
        if kind == "drc":
            arguments.append("--all-track-errors")
            if check["schematic_parity"]:
                arguments.append("--schematic-parity")
        arguments.extend(["--output", str(output / f"{kind}.json"), design["schematic" if kind == "erc" else "board"]])
        result.append((kind, arguments))
    if plan.get("fabrication") is not None:
        result.extend([
            ("gerbers", ["kicad-cli", "pcb", "export", "gerbers", "--layers",
                         ",".join(plan["fabrication"]["layers"]), "--no-protel-ext", "--precision", "6",
                         "--output", str(output / "gerbers") + "/", design["board"]]),
            ("drill", ["kicad-cli", "pcb", "export", "drill", "--format", "excellon",
                       "--drill-origin", "absolute", "--excellon-units", "mm",
                       "--excellon-zeros-format", "decimal", "--excellon-separate-th",
                       "--output", str(output / "drill") + "/", design["board"]]),
        ])
    return result


def execute(inputs: Path, plan: dict, output: Path, *, save=None) -> list[dict]:
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    for kind, arguments in steps(plan, output):
        log = output / f"{kind}.log"
        row = {"kind": kind, "command": arguments, "cwd": str(inputs), "exit_code": None, "log": str(log)}
        commands.append(row)
        if save is not None:
            save(commands)
        try:
            result = subprocess.run(
                arguments, cwd=inputs, env=environment(output / "config"),
                capture_output=True, text=True, timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.write_text(f"{kind}: {exc}\n", encoding="utf-8")
            raise EvidenceError(f"{kind}: native execution failed: {exc}") from exc
        log.write_text(result.stdout + result.stderr or "(no console output)\n", encoding="utf-8")
        row["exit_code"] = result.returncode
        if save is not None:
            save(commands)
        if result.returncode not in ((0, 5) if kind in ("erc", "drc") else (0,)):
            raise EvidenceError(f"{kind}: native command exited {result.returncode}; inspect {log}")
    return commands


def report(path: Path, kind: str, source: str, tool_version: str) -> tuple[dict[str, int], list]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{kind}: invalid native JSON report: {exc}") from exc
    if not isinstance(value, dict) or (
        value.get("$schema") != f"https://schemas.kicad.org/{kind}.v1.json"
        or value.get("source") != Path(source).name
        or value.get("kicad_version") != tool_version
        or value.get("coordinate_units") != "mm"
        or value.get("included_severities") != ["error", "warning", "exclusion"]
    ):
        raise EvidenceError(f"{kind}: report identity, tool version, units or included severities disagree")
    groups = []
    if kind == "erc":
        sheets = value.get("sheets")
        if not isinstance(sheets, list) or not sheets:
            raise EvidenceError("ERC report needs actual sheets")
        for sheet in sheets:
            if not isinstance(sheet, dict):
                raise EvidenceError("invalid ERC sheet")
            groups.append((text(sheet.get("path"), "sheet path"), sheet.get("violations")))
    else:
        groups = [(key, value.get(key)) for key in ("violations", "unconnected_items", "schematic_parity")]
    counts = {"error": 0, "warning": 0, "exclusion": 0}
    normalized = []
    for group, violations in groups:
        if not isinstance(violations, list):
            raise EvidenceError(f"{kind}: missing {group} list")
        for violation in violations:
            if not isinstance(violation, dict) or violation.get("severity") not in counts:
                raise EvidenceError(f"{kind}: invalid violation severity")
            counts[violation["severity"]] += 1
            items = violation.get("items")
            if not isinstance(items, list):
                raise EvidenceError(f"{kind}: violation items are missing")
            descriptions = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("pos"), dict):
                    raise EvidenceError(f"{kind}: invalid violation item")
                descriptions.append((text(item.get("description"), "item description"), item["pos"]))
            normalized.append([group, violation["severity"], text(violation.get("type"), "violation type"),
                               text(violation.get("description"), "violation description"),
                               sorted(descriptions, key=lambda item: json.dumps(item, sort_keys=True))])
    normalized.sort(key=lambda item: json.dumps(item, sort_keys=True))
    return counts, normalized


def output_paths(plan: dict, output: Path) -> list[Path]:
    paths = [output / f"{check['kind']}.json" for check in plan.get("checks", [])]
    fab = plan.get("fabrication")
    if fab is not None:
        stem = Path(plan["design"]["board"]).stem
        paths += [output / "gerbers" / f"{stem}-{layer.replace('.', '_')}.gbr" for layer in fab["layers"]]
        paths += [output / "drill" / f"{stem}-{kind}.drl" for kind in ("PTH", "NPTH")]
        job = output / "gerbers" / f"{stem}-job.gbrjob"
        if job.exists():
            paths.append(job)
        actual = {p for directory in ("gerbers", "drill") for p in (output / directory).rglob("*") if p.is_file()}
        expected = {p for p in paths if p.parent.name in ("gerbers", "drill")}
        if actual != expected:
            raise EvidenceError("native fabrication filenames differ from the explicitly requested output set")
    if any(not p.is_file() or p.stat().st_size == 0 or p.stat().st_size > 32 * 1024 * 1024 for p in paths):
        raise EvidenceError("native output is missing, empty or exceeds 32 MiB")
    return paths


def normalized_export(path: Path) -> str:
    data = path.read_text(encoding="utf-8")
    if path.suffix == ".gbrjob":
        try:
            value = json.loads(data)
            del value["Header"]["CreationDate"]
        except (ValueError, TypeError, KeyError) as exc:
            raise EvidenceError("invalid native Gerber job description") from exc
        return json.dumps(value, sort_keys=True)
    prefixes = ("%TF.CreationDate,", "G04 Created by KiCad ", "; DRILL file {KiCad ", "; #@! TF.CreationDate,")
    return "\n".join(line for line in data.splitlines() if not line.startswith(prefixes))


def fabrication_measurements(plan: dict, output: Path) -> dict:
    fab = plan.get("fabrication")
    if fab is None:
        return {}
    stem = Path(plan["design"]["board"]).stem
    features = {}
    for layer, minimum in fab["layers"].items():
        path = output / "gerbers" / f"{stem}-{layer.replace('.', '_')}.gbr"
        data = path.read_text(encoding="utf-8")
        if "%MOMM*%" not in data or "%FSLAX46Y46*%" not in data or not data.rstrip().endswith("M02*"):
            raise EvidenceError(f"{layer}: incomplete or unexpected Gerber format")
        count = sum(bool(re.search(r"D0[13]\*$", line)) and not line.startswith("G04") for line in data.splitlines())
        if count < minimum:
            raise EvidenceError(f"{layer}: {count} drawn features below required {minimum}")
        features[layer] = count
    hits = {}
    for kind, expected in fab["drill_hits"].items():
        data = (output / "drill" / f"{stem}-{kind.upper()}.drl").read_text(encoding="utf-8")
        if not data.startswith("M48\n") or "\nMETRIC\n" not in data or not data.rstrip().endswith("M30"):
            raise EvidenceError("incomplete or unexpected Excellon format")
        count = len(re.findall(r"^X-?\d+(?:\.\d+)?Y-?\d+(?:\.\d+)?$", data, re.MULTILINE))
        if count != expected:
            raise EvidenceError(f"{kind}: {count} drill hits, expected exactly {expected}")
        hits[kind] = count
    return {"drawn_features": features, "drill_hits": hits}
