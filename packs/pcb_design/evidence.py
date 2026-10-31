"""PCB evidence for KiCad 9 projects: stage checks, native runs and the bundled reference coupon.

The plan schema and acceptance rules are in evidence-contract.md beside this file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = "pcb/PLAN.json"
REVIEW = "pcb/REVIEW.md"
RESULTS_DIR = "pcb/results"
RESULTS = RESULTS_DIR + "/RESULTS.json"
INPUTS_DIR = RESULTS_DIR + "/inputs"
LIMIT = 32 * 1024 * 1024
KICAD_PYTHON = "/usr/bin/python3"
STAGES = ("specification", "design", "verification", "review")


class EvidenceError(ValueError):
    pass


# Project records -------------------------------------------------------------------------------

def project_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise EvidenceError(f"expected a project-relative file, got {relative!r}")
    try:
        path = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"{relative}: {exc}") from exc
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size == 0:
        raise EvidenceError(f"{relative}: expected a nonempty file inside the project")
    return path


def record(root: Path, relative: str) -> dict:
    try:
        value = json.loads(project_file(root, relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{relative}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{relative}: expected a JSON object")
    return value


def names(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise EvidenceError(f"{field}: expected distinct nonempty strings")
    return value


def current_files(root: Path, payload: dict, required: list[str], *, field: str = "inputs") -> None:
    copies = payload.get(field)
    if not isinstance(copies, dict) or not set(required) <= copies.keys():
        raise EvidenceError(f"{field}: snapshots must include every required file")
    for source, snapshot in copies.items():
        source_path, copy_path = project_file(root, source), project_file(root, snapshot)
        if source_path.samefile(copy_path) or source_path.read_bytes() != copy_path.read_bytes():
            raise EvidenceError(f"{field}: missing independent copy or changed file {source}")


def text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field}: expected nonempty text")
    return value


def integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise EvidenceError(f"{field}: expected a nonnegative integer")
    return value


# KiCad input closure ---------------------------------------------------------------------------

def children(tree: list, tag: str) -> list[list]:
    return [node for node in tree if isinstance(node, list) and node and str(node[0]) == tag]


def child(tree: list, tag: str) -> list:
    found = children(tree, tag)
    if len(found) != 1 or len(found[0]) < 2:
        raise EvidenceError(f"KiCad {tag}: expected exactly one entry")
    return found[0]


def parse(root: Path, relative: str, tag: str) -> list:
    try:
        import sexpdata
    except ImportError as exc:
        raise EvidenceError("reading KiCad files needs the sexpdata package (pip install 'sexpdata>=1.0.2,<2')") from exc
    path = project_file(root, relative)
    if path.stat().st_size > LIMIT:
        raise EvidenceError(f"{relative}: exceeds 32 MiB")
    try:
        tree = sexpdata.loads(path.read_text(encoding="utf-8"), line_comment="#")
    except (ValueError, AssertionError, IndexError, RecursionError, UnicodeError) as exc:
        raise EvidenceError(f"{relative}: invalid KiCad expression: {exc}") from exc
    if not isinstance(tree, list) or not tree or str(tree[0]) != tag:
        raise EvidenceError(f"{relative}: expected {tag}")
    return tree


def validate_specification(root: Path) -> dict:
    plan = record(root, PLAN)
    text(plan.get("objective"), "objective")
    names(plan.get("requirements"), "requirements")
    names(plan.get("limitations"), "limitations")
    return plan


def _local(root: Path, directory: Path, raw: object, project_directory: Path) -> str:
    value = text(raw, "local path")
    if value.startswith("${KIPRJMOD}/"):
        value = value[len("${KIPRJMOD}/"):]
        directory = project_directory
    if "${" in value or "$(" in value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise EvidenceError(f"unsupported external or variable path: {raw}")
    result = (directory / value).as_posix()
    if result.startswith(RESULTS_DIR + "/"):
        raise EvidenceError("design inputs cannot refer to pcb/results")
    project_file(root, result)
    return result


def _settings(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if ("exclusion" in key or key in ("text_variables", "page_layout_descr_file")) and item:
                raise EvidenceError(f"{key}: exclusions, project variables and custom drawing sheets are unsupported")
            if key in ("rule_severities", "erc_severities") and (
                not isinstance(item, dict) or any(level not in ("error", "warning") for level in item.values())
            ):
                raise EvidenceError(f"{key}: disabled or unknown check severities are unsupported")
            _settings(item)
    elif isinstance(value, list):
        for item in value:
            _settings(item)


def input_closure(root: Path, plan: dict, *, all_design: bool = False) -> tuple[list[str], list[str]]:
    design = plan.get("design")
    if not isinstance(design, dict):
        raise EvidenceError("design: declare a native project and the selected schematic or board")
    project = text(design.get("project"), "design.project")
    if Path(project).suffix != ".kicad_pro":
        raise EvidenceError("design.project: expected .kicad_pro")
    project_file(root, project)
    if Path(project).as_posix() != project or project.startswith(RESULTS_DIR + "/"):
        raise EvidenceError("design.project: use a canonical project-relative path outside results")
    directory = Path(project).parent
    settings = record(root, project)
    _settings(settings)
    required = {PLAN, project}
    for relative in (str(Path(project).with_suffix(".kicad_dru")),):
        if (root / relative).exists():
            data = project_file(root, relative).read_text(encoding="utf-8")
            if re.search(r"\(\s*severity\s+(?:ignore|exclusion)\s*\)", data):
                raise EvidenceError("custom rules cannot suppress or exclude checks")
            required.add(relative)
    checks = plan.get("checks", [])
    need_board = all_design and "board" in design or any(c["kind"] == "drc" for c in checks) or plan.get("fabrication") is not None
    need_schematic = all_design and "schematic" in design or any(
        c["kind"] == "erc" or c.get("schematic_parity") for c in checks
    )
    tables = {}
    for table, tag, kind in (("sym-lib-table", "sym_lib_table", "KiCad"), ("fp-lib-table", "fp_lib_table", "KiCad")):
        relative = (directory / table).as_posix()
        entries = {}
        if (root / relative).exists():
            required.add(relative)
            tree = parse(root, relative, tag)
            for entry in children(tree, "lib"):
                name = text(child(entry, "name")[1], "library name")
                if name in entries or str(child(entry, "type")[1]) != kind:
                    raise EvidenceError("use distinct project-local KiCad library names")
                if children(entry, "options") and child(entry, "options")[1]:
                    raise EvidenceError("library options are unsupported")
                uri = text(child(entry, "uri")[1], "library uri")
                footprint_library = table == "fp-lib-table"
                value = uri.removeprefix("${KIPRJMOD}/")
                if "${" in value or "$(" in value or Path(value).is_absolute() or ".." in Path(value).parts:
                    raise EvidenceError("library uri must be project-local")
                path = (directory / value).as_posix()
                resolved = (root / path).resolve()
                if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                    raise EvidenceError("library uri must resolve inside the project")
                if footprint_library:
                    if not resolved.is_dir() or resolved.suffix != ".pretty":
                        raise EvidenceError("footprint libraries must be local .pretty directories")
                else:
                    parse(root, path, "kicad_symbol_lib")
                    required.add(path)
                entries[name] = path
        tables[table] = entries

    def library_item(identity: str, table: str) -> None:
        parts = identity.split(":")
        if len(parts) != 2 or parts[0] not in tables[table] or not parts[1] or "/" in parts[1] or "\\" in parts[1]:
            raise EvidenceError(f"{identity}: needs a project-local {table} entry")
        if table == "fp-lib-table":
            relative = tables[table][parts[0]] + "/" + parts[1] + ".kicad_mod"
            parse(root, relative, "footprint")
            required.add(relative)

    layers = []
    if need_board:
        board_path = text(design.get("board"), "design.board")
        if board_path != str(Path(project).with_suffix(".kicad_pcb")):
            raise EvidenceError("board and project must have the same directory and stem")
        board = parse(root, board_path, "kicad_pcb")
        required.add(board_path)
        layers = [str(row[1]) for row in child(board, "layers")[1:] if isinstance(row, list) and len(row) >= 3]
        if not {"F.Cu", "B.Cu"} <= set(layers) or len(children(board, "footprint")) < 1:
            raise EvidenceError("a nonempty board with at least two copper layers is required")
        zones = children(board, "zone")
        if zones and not plan.get("zone_refill"):
            raise EvidenceError("copper zones require explicit zone_refill: true; stored fills are not trusted")
        if plan.get("zone_refill") and not zones:
            raise EvidenceError("zone_refill requires actual board copper zones")
        zone_ids = []
        for zone in zones:
            if children(zone, "keepout") or children(zone, "rule_area") or children(zone, "layers"):
                raise EvidenceError("rule areas and multi-layer zone objects are unsupported; use single-layer copper zones")
            layer = str(child(zone, "layer")[1])
            if layer not in layers or not layer.endswith(".Cu"):
                raise EvidenceError("zones must belong to an enabled copper layer")
            zone_ids.append(text(child(zone, "uuid")[1], "original zone identity"))
            if not children(zone, "polygon"):
                raise EvidenceError("copper zones need original polygon outlines")
        if len(zones) > 256 or len(zone_ids) != len(set(zone_ids)):
            raise EvidenceError("use at most 256 copper zones with distinct original identities")
        if not any(str(child(item, "layer")[1]) == "Edge.Cuts" for tag in ("gr_line", "gr_rect", "gr_arc", "gr_poly", "gr_circle") for item in children(board, tag)):
            raise EvidenceError("board needs actual Edge.Cuts geometry")
        pads = 0
        for footprint in children(board, "footprint"):
            if children(footprint, "zone"):
                raise EvidenceError("footprint-local zones and rule areas are unsupported")
            library_item(text(footprint[1] if len(footprint) > 1 else None, "footprint identity"), "fp-lib-table")
            for pad in children(footprint, "pad"):
                pads += 1
                for drill in children(pad, "drill"):
                    if len(drill) != 2 or not isinstance(drill[1], (int, float)) or drill[1] <= 0:
                        raise EvidenceError("only positive round through-hole drills are supported")
        if pads < 2 or not any(len(net) >= 3 and net[2] for net in children(board, "net")):
            raise EvidenceError("board needs at least two pads and a named electrical net")
        for via in children(board, "via"):
            if any(str(atom) in ("blind", "micro") for atom in via[1:2]) or [str(v) for v in child(via, "layers")[1:]] != ["F.Cu", "B.Cu"]:
                raise EvidenceError("only full-through vias are supported")

    if need_schematic:
        schematic = text(design.get("schematic"), "design.schematic")
        if schematic != str(Path(project).with_suffix(".kicad_sch")):
            raise EvidenceError("root schematic and project must have the same directory and stem")
        seen, active = set(), set()
        symbols = 0

        def visit(relative: str) -> None:
            nonlocal symbols
            if relative in active:
                raise EvidenceError("cyclic hierarchical schematic")
            if relative in seen:
                return
            if len(seen) >= 64:
                raise EvidenceError("schematic exceeds 64 distinct sheets")
            seen.add(relative)
            active.add(relative)
            tree = parse(root, relative, "kicad_sch")
            required.add(relative)
            for symbol in children(tree, "symbol"):
                symbols += 1
                library_item(str(child(symbol, "lib_id")[1]), "sym-lib-table")
                for prop in children(symbol, "property"):
                    if len(prop) >= 3 and prop[1] == "Footprint" and prop[2]:
                        library_item(str(prop[2]), "fp-lib-table")
            for sheet in children(tree, "sheet"):
                filename = [p[2] for p in children(sheet, "property") if len(p) >= 3 and p[1] == "Sheetfile"]
                if len(filename) != 1:
                    raise EvidenceError("hierarchical sheet needs one Sheetfile")
                visit(_local(root, Path(relative).parent, filename[0], directory))
            active.remove(relative)

        visit(schematic)
        if symbols < 1:
            raise EvidenceError("schematic must contain actual symbols")
    if not need_board and not need_schematic:
        raise EvidenceError("select a schematic or board operation")
    if len(required) > 256 or sum(project_file(root, p).stat().st_size for p in required) > 128 * 1024 * 1024:
        raise EvidenceError("input closure exceeds 256 files or 128 MiB")
    return sorted(required), layers


def validate_plan(root: Path, *, all_design: bool = False) -> tuple[dict, list[str]]:
    plan = validate_specification(root)
    if type(plan.get("zone_refill", False)) is not bool:
        raise EvidenceError("zone_refill must be an explicit boolean")
    checks = plan.get("checks", [])
    if not isinstance(checks, list) or len(checks) > 2 or any(not isinstance(c, dict) for c in checks):
        raise EvidenceError("checks: choose at most one ERC and one DRC")
    kinds = names([c.get("kind") for c in checks], "check kinds", allow_empty=True)
    if not set(kinds) <= {"erc", "drc"}:
        raise EvidenceError("check kind must be erc or drc")
    for check in checks:
        integer(check.get("max_errors"), "max_errors")
        integer(check.get("max_warnings"), "max_warnings")
        if check["kind"] == "drc":
            if type(check.get("schematic_parity")) is not bool:
                raise EvidenceError("DRC must explicitly enable or disable schematic_parity")
        elif "schematic_parity" in check:
            raise EvidenceError("schematic_parity belongs to DRC only")
    fab = plan.get("fabrication")
    if fab is not None:
        if not isinstance(fab, dict) or not isinstance(fab.get("layers"), dict) or not fab["layers"]:
            raise EvidenceError("fabrication.layers: map requested layer names to minimum drawn feature counts")
        for layer, count in fab["layers"].items():
            if not isinstance(layer, str) or not re.fullmatch(r"(?:[FB]\.(?:Cu|Mask|SilkS|Paste)|In[1-9][0-9]?\.Cu|Edge\.Cuts)", layer):
                raise EvidenceError("unsupported fabrication layer")
            integer(count, "minimum drawn features")
        holes = fab.get("drill_hits")
        if not isinstance(holes, dict) or set(holes) != {"pth", "npth"}:
            raise EvidenceError("drill_hits: declare exact pth and npth hit counts")
        for count in holes.values():
            integer(count, "drill hits")
    if not checks and fab is None and not all_design:
        raise EvidenceError("select at least one native check or fabrication export")
    if plan.get("zone_refill") and not (
        any(c["kind"] == "drc" for c in checks) or fab is not None
        or all_design and isinstance(plan.get("design"), dict) and "board" in plan["design"]
    ):
        raise EvidenceError("zone_refill needs a selected board operation, not ERC alone")
    inputs, layers = input_closure(root, plan, all_design=all_design)
    if fab is not None:
        mandatory = {layer for layer in layers if layer.endswith(".Cu")} | {"Edge.Cuts"}
        if not mandatory <= fab["layers"].keys():
            raise EvidenceError("fabrication must include every enabled copper layer and Edge.Cuts")
        if not fab["layers"].keys() <= set(layers) | {"Edge.Cuts"}:
            raise EvidenceError("fabrication requested a layer not enabled in the board")
        if fab["layers"]["Edge.Cuts"] < 1 or fab["layers"]["F.Cu"] + fab["layers"]["B.Cu"] < 1:
            raise EvidenceError("fabrication requires nonempty outline and copper")
    return plan, inputs


# Native KiCad 9 commands; no project input is rewritten -------------------------------------------

MAX_CONSOLE_BYTES = 32 * 1024 * 1024


def run_logged(command: list[str], *, root: Path, log: Path, timeout: float, env: dict[str, str]) -> tuple[int, str]:
    """Stream one command's console to `log`; stop it on timeout or runaway output, and clean up its process group."""
    deadline = time.monotonic() + timeout

    def limit() -> str:
        if time.monotonic() >= deadline:
            return f"native command exceeded {timeout:g} seconds"
        if log.stat().st_size > MAX_CONSOLE_BYTES:
            return f"native console output exceeded {MAX_CONSOLE_BYTES} bytes"
        return ""

    stopped = ""
    with log.open("w", encoding="utf-8") as stream, subprocess.Popen(
        command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            while process.poll() is None:
                if stopped := limit():
                    break
                time.sleep(0.05)
        finally:
            finished = process.poll() is not None
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    if finished and not stopped:
                        stopped = "native command left owned child processes running"
                except ProcessLookupError:
                    pass
            elif not finished:
                process.kill()
            exit_code = process.wait()
    return exit_code, stopped or limit()


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


def steps(plan: dict, output: Path, kicad_python: str) -> list[tuple[str, list[str]]]:
    result = []
    design = plan["design"]
    if plan.get("zone_refill"):
        result.append(("refill", [
            kicad_python, "-I", str(HERE / "refill.py"), design["board"],
            "--output", str(output), "--expected-version", version(),
        ]))
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


def working_directory(inputs: Path, plan: dict, output: Path) -> Path:
    return output / "work" if plan.get("zone_refill") else inputs


def execute(inputs: Path, plan: dict, output: Path, kicad_python: str, *, save=None) -> list[dict]:
    output.mkdir(parents=True, exist_ok=False)
    work = working_directory(inputs, plan, output)
    required = []
    if plan.get("zone_refill"):
        frozen, required = validate_plan(inputs)
        if frozen != plan:
            raise EvidenceError("refill input plan differs from the selected plan")
        for relative in required:
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inputs / relative, destination)
    commands = []
    for kind, arguments in steps(plan, output, kicad_python):
        log = output / f"{kind}.log"
        row = {"kind": kind, "command": arguments, "cwd": str(work), "exit_code": None, "log": str(log)}
        commands.append(row)
        if save is not None:
            save(commands)
        try:
            row["exit_code"], stopped = run_logged(
                arguments, root=work, env=environment(output / "config"),
                log=log, timeout=180,
            )
        except OSError as exc:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"{kind}: {exc}\n")
            raise EvidenceError(f"{kind}: native execution failed: {exc}") from exc
        if not log.stat().st_size:
            log.write_text("(no console output)\n", encoding="utf-8")
        if stopped:
            row["stop_reason"] = stopped
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"{stopped}\n")
        if save is not None:
            save(commands)
        if stopped:
            raise EvidenceError(f"{kind}: {stopped}; inspect {log}")
        if row["exit_code"] not in ((0, 5) if kind in ("erc", "drc") else (0,)):
            raise EvidenceError(f"{kind}: native command exited {row['exit_code']}; inspect {log}")
    for relative in required:
        if relative != plan["design"]["board"] and (work / relative).read_bytes() != (inputs / relative).read_bytes():
            raise EvidenceError(f"native execution modified copied settings or dependencies: {relative}")
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
    if plan.get("zone_refill"):
        paths += [output / "refill.json", output / "refill-unfilled.kicad_pcb", output / "work" / plan["design"]["board"]]
        if (output / "refill-rules.rpt").exists():
            paths.append(output / "refill-rules.rpt")
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
    prefixes = ("%TF.CreationDate,", "G04 Created by KiCad ", "; DRILL file {KiCad ", "; #@! TF.CreationDate,", "** Created on ")
    return "\n".join(line for line in data.splitlines() if not line.startswith(prefixes))


def refill_measurements(plan: dict, output: Path, tool_version: str) -> dict:
    if not plan.get("zone_refill"):
        return {}
    value = record(output, "refill.json")
    if (
        value.get("operation") != "pcbnew.ZONE_FILLER"
        or value.get("kicad_version") != tool_version
        or value.get("board") != plan["design"]["board"]
        or value.get("old_fills_discarded") is not True
        or value.get("non_fill_design_unchanged") is not True
        or not isinstance(value.get("zones"), list) or not value["zones"]
    ):
        raise EvidenceError("refill report does not identify the selected native operation and board")
    return {"zone_refill": value}


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


# Saved evidence against inputs and a fresh, temporary native replay --------------------------------

def validate_verification(root: Path, kicad_python: str = KICAD_PYTHON) -> dict:
    root = root.resolve()
    plan, inputs = validate_plan(root)
    result = record(root, RESULTS)
    operation = "kicad-cli+pcbnew" if plan.get("zone_refill") else "kicad-cli"
    if result.get("status") != "complete" or result.get("operation") != operation:
        raise EvidenceError("PCB execution has no completed native command record")
    tool_version = version()
    if result.get("kicad_version") != tool_version:
        raise EvidenceError("KiCad version differs from the recorded execution")
    expected_inputs = {p: f"{INPUTS_DIR}/{p}" for p in inputs}
    if result.get("inputs") != expected_inputs:
        raise EvidenceError("input copies must include exactly the selected native dependency closure and plan")
    current_files(root, result, inputs)
    output = root / RESULTS_DIR / "native"
    paths = output_paths(plan, output)
    outputs = {p.relative_to(root).as_posix(): f"{RESULTS_DIR}/retained/{p.relative_to(output).as_posix()}" for p in paths}
    if result.get("outputs") != outputs:
        raise EvidenceError("retain independent copies of every native report and fabrication file")
    current_files(root, result, list(outputs), field="outputs")
    commands = result.get("commands")
    expected_steps = steps(plan, output, kicad_python)
    if not isinstance(commands, list) or len(commands) != len(expected_steps):
        raise EvidenceError("native command records do not match selected operations")
    checks = {c["kind"]: c for c in plan.get("checks", [])}
    measured, reports = {}, {}
    for row, (kind, arguments) in zip(commands, expected_steps):
        if not isinstance(row, dict) or (
            row.get("kind") != kind or row.get("command") != arguments
            or row.get("cwd") != str(working_directory(root / INPUTS_DIR, plan, output))
            or row.get("log") != str(output / f"{kind}.log")
            or type(row.get("exit_code")) is not int
        ):
            raise EvidenceError("native command, working directory or log identity disagrees")
        project_file(root, (output / f"{kind}.log").relative_to(root).as_posix())
        if kind in checks:
            counts, normalized = report(
                output / f"{kind}.json", kind, plan["design"]["schematic" if kind == "erc" else "board"], tool_version,
            )
            if counts["exclusion"] or counts["error"] > checks[kind]["max_errors"] or counts["warning"] > checks[kind]["max_warnings"]:
                raise EvidenceError(f"{kind}: {counts} violates the original acceptance limits")
            if row["exit_code"] != (5 if any(counts.values()) else 0):
                raise EvidenceError("native exit code and report violation counts disagree")
            reports[kind] = normalized
            measured[kind] = counts
        elif row["exit_code"] != 0:
            raise EvidenceError(f"{kind}: export did not succeed")
    measured.update(fabrication_measurements(plan, output))
    measured.update(refill_measurements(plan, output, tool_version))
    # Replay a separate copy: KiCad may write local cache/config files even for checks.
    with tempfile.TemporaryDirectory(prefix="pcb-check-") as directory:
        temporary = Path(directory)
        replay_inputs = temporary / "inputs"
        for relative in inputs:
            destination = replay_inputs / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), destination)
        replay = temporary / "native"
        replay_commands = execute(replay_inputs, plan, replay, kicad_python)
        replay_paths = output_paths(plan, replay)
        if {p.relative_to(replay) for p in replay_paths} != {p.relative_to(output) for p in paths}:
            raise EvidenceError("native replay produced a different set of output files")
        for original, fresh in zip(commands, replay_commands):
            if original["exit_code"] != fresh["exit_code"]:
                raise EvidenceError("native replay exit code disagrees with saved execution")
        for kind, expected in reports.items():
            _, normalized = report(
                replay / f"{kind}.json", kind, plan["design"]["schematic" if kind == "erc" else "board"], tool_version,
            )
            if normalized != expected:
                raise EvidenceError(f"{kind}: saved violations disagree with independent native replay")
        for path in paths:
            if path.suffix in (".gbr", ".drl", ".gbrjob", ".rpt") and normalized_export(path) != normalized_export(replay / path.relative_to(output)):
                raise EvidenceError(f"{path.name}: exported geometry differs from independent native replay")
            if path.suffix == ".kicad_pcb" and path.read_bytes() != (replay / path.relative_to(output)).read_bytes():
                raise EvidenceError(f"{path.name}: refilled board differs from independent native replay")
        if refill_measurements(plan, replay, tool_version) != refill_measurements(plan, output, tool_version):
            raise EvidenceError("zone refill measurements differ from independent native replay")
        for relative in inputs:
            if (replay_inputs / relative).read_bytes() != project_file(root, relative).read_bytes():
                raise EvidenceError("native replay modified a design input")
    current_files(root, result, inputs)
    return measured


def check_stage(stage: str, root: Path, kicad_python: str = KICAD_PYTHON) -> dict:
    """Raise EvidenceError unless `stage` is complete; return any measured values."""
    if stage == "specification":
        validate_specification(root)
        return {}
    if stage == "design":
        validate_plan(root, all_design=True)
        return {}
    if stage not in ("verification", "review"):
        raise EvidenceError(f"unknown PCB stage: {stage}")
    measured = validate_verification(root, kicad_python)
    if stage == "review":
        project_file(root, REVIEW)
    return measured


# Run only the selected native operations from independent copied inputs ----------------------------

def run_analysis(root: Path, kicad_python: str = KICAD_PYTHON) -> dict:
    root = root.resolve()
    plan, required = validate_plan(root)
    tool_version = version()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    inputs = {}
    for relative in required:
        target = f"{INPUTS_DIR}/{relative}"
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / target)
        inputs[relative] = target
    result = {
        "operation": "kicad-cli+pcbnew" if plan.get("zone_refill") else "kicad-cli",
        "status": "running", "kicad_version": tool_version,
        "inputs": inputs, "commands": [], "outputs": {},
    }

    def save(commands=None) -> None:
        if commands is not None:
            result["commands"] = commands
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        frozen_plan, _ = validate_plan(root / INPUTS_DIR)
        if frozen_plan != plan:
            raise EvidenceError("plan changed while copying inputs")
        output = root / RESULTS_DIR / "native"
        execute(root / INPUTS_DIR, plan, output, kicad_python, save=save)
        for path in output_paths(plan, output):
            retained = f"{RESULTS_DIR}/retained/{path.relative_to(output).as_posix()}"
            (root / retained).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / retained)
            result["outputs"][path.relative_to(root).as_posix()] = retained
        result["status"] = "complete"
        save()
        measured = validate_verification(root, kicad_python)
    except (EvidenceError, OSError, UnicodeError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise
    return measured


# The bundled original reference coupons ----------------------------------------------------------

def prepare_reference(root: Path, *, zones: bool = False) -> None:
    """An original two-testpoint continuity coupon; with zones, four same-net copper zones refilled on a copy."""
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(HERE / "references/coupon", root / "design")
    (root / "pcb").mkdir()
    plan = {
        "objective": "Check an original two-testpoint continuity coupon and export its exact manufacturing geometry.",
        "requirements": [
            "ERC, DRC and schematic-board parity have no errors, warnings or exclusions.",
            "Export all copper, both solder masks and a nonempty outline at the absolute origin.",
            "Produce exactly two plated round drill hits and zero nonplated hits.",
        ],
        "limitations": [
            "An original connectivity/geometry reference, not a functional circuit or physical prototype.",
            "No field-solved SI/PI, thermal, assembly yield, fab acceptance or energizing authorization.",
        ],
        "design": {key: f"design/coupon.{suffix}" for key, suffix in (
            ("project", "kicad_pro"), ("schematic", "kicad_sch"), ("board", "kicad_pcb"),
        )},
        "checks": [
            {"kind": "erc", "max_errors": 0, "max_warnings": 0},
            {"kind": "drc", "max_errors": 0, "max_warnings": 0, "schematic_parity": True},
        ],
        "fabrication": {
            "layers": {"F.Cu": 3, "B.Cu": 2, "F.Mask": 2, "B.Mask": 2, "Edge.Cuts": 4},
            "drill_hits": {"pth": 2, "npth": 0},
        },
    }
    if zones:
        shutil.copyfile(HERE / "references/four-layer-zones.kicad_pcb", root / "design/coupon.kicad_pcb")
        plan["objective"] = "Refill copied four-layer copper, then check and export that same board without changing the original."
        plan["requirements"].append("Discard old zone fills; preserve original outlines, nets, pads and project settings.")
        plan["limitations"].append("Continuity coupon only; the four same-net planes are not a production stackup or SI/PI result.")
        plan["zone_refill"] = True
        plan["fabrication"]["layers"].update({"F.Cu": 3, "In1.Cu": 3, "In2.Cu": 3, "B.Cu": 3})
    (root / PLAN).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pcb-evidence", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check that one stage's evidence is complete (the project is not modified)")
    check.add_argument("--project-root", default=".")
    check.add_argument("--stage", choices=STAGES, required=True)
    run = commands.add_parser("run", help="run the plan's selected KiCad checks/exports into a new pcb/results")
    run.add_argument("--project-root", default=".")
    reference = commands.add_parser("reference", help="build the bundled original coupon in a new directory and run it")
    reference.add_argument("directory", type=Path, help="a directory that does not exist yet")
    reference.add_argument("--zones", action="store_true", help="the four-layer coupon with copper zones refilled on a copy")
    for sub in (check, run, reference):
        sub.add_argument("--kicad-python", default=KICAD_PYTHON,
                         help="absolute path of the Python with KiCad's pcbnew binding, for zone refill (default %(default)s)")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            measured = check_stage(args.stage, Path(args.project_root).resolve(), args.kicad_python)
        elif args.command == "run":
            measured = run_analysis(Path(args.project_root), args.kicad_python)
        else:
            prepare_reference(args.directory.resolve(), zones=args.zones)
            measured = run_analysis(args.directory, args.kicad_python)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if measured:
        print(json.dumps(measured, indent=2))
    if args.command == "check":
        print(f"OK: pcb {args.stage} evidence complete; not physical qualification or fabrication approval")
    else:
        print("PASS: selected native PCB checks/exports only; no physical qualification or manufacture approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
