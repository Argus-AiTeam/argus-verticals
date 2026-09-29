"""Resolve a local KiCad input closure before executing any native commands."""
from __future__ import annotations

import re
from pathlib import Path

import sexpdata

from argus_verticals.hardware.shared.evidence import EvidenceError, names, project_file, record

PLAN = "pcb/PLAN.json"
RESULTS_DIR = "pcb/results"
RESULTS = RESULTS_DIR + "/RESULTS.json"
INPUTS_DIR = RESULTS_DIR + "/inputs"
LIMIT = 32 * 1024 * 1024


def text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field}: expected nonempty text")
    return value


def integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise EvidenceError(f"{field}: expected a nonnegative integer")
    return value


def children(tree: list, tag: str) -> list[list]:
    return [node for node in tree if isinstance(node, list) and node and str(node[0]) == tag]


def child(tree: list, tag: str) -> list:
    found = children(tree, tag)
    if len(found) != 1 or len(found[0]) < 2:
        raise EvidenceError(f"KiCad {tag}: expected exactly one entry")
    return found[0]


def parse(root: Path, relative: str, tag: str) -> list:
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
        if children(board, "zone"):
            raise EvidenceError("copper zones and rule areas need a separate refill-aware implementation; not supported here")
        if not any(str(child(item, "layer")[1]) == "Edge.Cuts" for tag in ("gr_line", "gr_rect", "gr_arc", "gr_poly", "gr_circle") for item in children(board, tag)):
            raise EvidenceError("board needs actual Edge.Cuts geometry")
        pads = 0
        for footprint in children(board, "footprint"):
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
