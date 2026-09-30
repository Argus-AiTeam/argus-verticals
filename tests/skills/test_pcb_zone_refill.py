from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import sexpdata

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.pcb_design import native
from argus_verticals.pcb_design.design import RESULTS, children, validate_plan
from argus_verticals.pcb_design.evidence import validate_verification
from argus_verticals.pcb_design.run_analysis import run_analysis
from argus_verticals.pcb_design.run_zone_reference import prepare_reference, run_reference


def load(root, relative="pcb/PLAN.json"):
    return json.loads((root / relative).read_text())


def save(root, value, relative="pcb/PLAN.json"):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


def edit_board(root, mutate):
    path = root / "design/coupon.kicad_pcb"
    tree = sexpdata.loads(path.read_text())
    mutate(tree)
    path.write_text(sexpdata.dumps(tree) + "\n")


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if shutil.which("kicad-cli") is None:
        pytest.skip("KiCad 9 is required for native copper refill")
    root = tmp_path_factory.mktemp("pcb-zone") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    root = Path(shutil.copytree(reference, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(reference), str(root)))
    return root


def test_native_four_layer_refill_uses_one_board_and_preserves_inputs(reference):
    values = validate_verification(reference)
    assert values["erc"] == values["drc"] == {"error": 0, "warning": 0, "exclusion": 0}
    assert values["drill_hits"] == {"pth": 2, "npth": 0}
    zones = values["zone_refill"]["zones"]
    assert {row["layer"] for row in zones} == {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}
    # Four 18 x 8 mm rectangles; native corner rounding removes less than 0.02 mm2.
    assert all(row["filled_area_mm2"] == pytest.approx(144, abs=0.02) for row in zones)
    result = load(reference, RESULTS)
    assert [row["kind"] for row in result["commands"]] == ["refill", "erc", "drc", "gerbers", "drill"]
    assert {row["cwd"] for row in result["commands"]} == {str(reference / "pcb/results/native/work")}
    for source, copy in result["inputs"].items():
        assert (reference / source).read_bytes() == (reference / copy).read_bytes()
    source = (reference / "design/coupon.kicad_pcb").read_text()
    filled = (reference / "pcb/results/native/work/design/coupon.kicad_pcb").read_text()
    assert "(filled_polygon" not in source and filled.count("(filled_polygon") == 4


@pytest.mark.parametrize("selection", ["drc", "fabrication"])
def test_refill_does_not_force_other_checks(planned, selection):
    plan = load(planned)
    if selection == "fabrication":
        plan["checks"] = []
    else:
        plan["checks"] = [{"kind": "drc", "max_errors": 0, "max_warnings": 0, "schematic_parity": False}]
        plan["fabrication"] = None
    plan["design"].pop("schematic")
    save(planned, plan)
    values = run_analysis(planned)
    expected = {"zone_refill", "drc"} if selection == "drc" else {"zone_refill", "drawn_features", "drill_hits"}
    assert set(values) == expected
    assert "design/coupon.kicad_sch" not in load(planned, RESULTS)["inputs"]


@pytest.mark.parametrize("mutation", ["not_enabled", "wrong_type", "erc_only", "rule_area", "multi_layer", "footprint_zone", "non_copper"])
def test_unsupported_refill_requests_fail_before_native_work(planned, mutation):
    plan = load(planned)
    if mutation == "not_enabled":
        del plan["zone_refill"]
    elif mutation == "wrong_type":
        plan["zone_refill"] = 1
    elif mutation == "erc_only":
        plan["checks"] = plan["checks"][:1]
        plan["fabrication"] = None
    else:
        def mutate(tree):
            zone = children(tree, "zone")[0]
            if mutation == "rule_area":
                zone.append([sexpdata.Symbol("keepout"), [sexpdata.Symbol("copperpour"), sexpdata.Symbol("not_allowed")]])
            elif mutation == "multi_layer":
                children(zone, "layer")[0][:] = [sexpdata.Symbol("layers"), "F.Cu", "B.Cu"]
            elif mutation == "footprint_zone":
                tree.remove(zone)
                children(tree, "footprint")[0].append(zone)
            else:
                children(zone, "layer")[0][1] = "F.SilkS"
        edit_board(planned, mutate)
    save(planned, plan)
    with pytest.raises(EvidenceError):
        run_analysis(planned)
    assert not (planned / "pcb/results").exists()


def test_checker_is_read_only(reference):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    validate_verification(reference)
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation", ["board", "area", "layer", "original", "skip_refill", "wrong_cwd"])
def test_matching_copies_cannot_hide_wrong_refill_evidence(work, mutation):
    result = load(work, RESULTS)
    if mutation == "skip_refill":
        result["commands"].pop(0)
    elif mutation == "wrong_cwd":
        result["commands"][2]["cwd"] = str(work / "pcb/results/inputs")
    elif mutation == "original":
        (work / "design/coupon.kicad_pcb").write_text("(invalid)\n")
    else:
        if mutation == "board":
            source = "pcb/results/native/work/design/coupon.kicad_pcb"
            path = work / source
            tree = sexpdata.loads(path.read_text())
            polygon = children(children(tree, "zone")[0], "filled_polygon")[0]
            children(children(polygon, "pts")[0], "xy")[0][1] += 0.1
            path.write_text(sexpdata.dumps(tree) + "\n")
        else:
            source = "pcb/results/native/refill.json"
            report = load(work, source)
            report["zones"][0]["filled_area_mm2" if mutation == "area" else "layer"] = 1 if mutation == "area" else "Edge.Cuts"
            save(work, report, source)
        shutil.copyfile(work / source, work / result["outputs"][source])
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        validate_verification(work)


def test_missing_native_python_is_a_preserved_failure(planned, monkeypatch):
    monkeypatch.setenv("ARGUS_KICAD_PYTHON", "/no/such/kicad-python")
    with pytest.raises(EvidenceError, match="refill: native execution failed"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert result["status"] == "failed" and result["commands"][0]["exit_code"] is None
    assert not (planned / "pcb/results/native/gerbers").exists()
    with pytest.raises(FileExistsError):
        run_analysis(planned)


def test_broken_custom_rules_are_not_silently_ignored(planned):
    (planned / "design/coupon.kicad_dru").write_text('(version 1)\n(rule "broken"\n')
    with pytest.raises(EvidenceError, match="refill: native command exited"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert result["status"] == "failed"
    assert "custom rules" in (planned / "pcb/results/native/refill.log").read_text()


def test_closure_keeps_every_enabled_copper_layer(planned):
    plan = load(planned)
    del plan["fabrication"]["layers"]["In2.Cu"]
    save(planned, plan)
    with pytest.raises(EvidenceError, match="every enabled copper layer"):
        validate_plan(planned)


@pytest.mark.parametrize("design", [None, 1, []])
def test_invalid_design_in_refill_scope_is_an_explicit_issue(planned, design):
    plan = load(planned)
    plan.update(design=design, checks=[], fabrication=None)
    save(planned, plan)
    with pytest.raises(EvidenceError, match="selected board operation"):
        validate_plan(planned, all_design=True)


@pytest.mark.parametrize("location", ["project", "custom_rules"])
def test_native_refill_obeys_original_edge_clearance(planned, location):
    if location == "custom_rules":
        (planned / "design/coupon.kicad_dru").write_text('(version 1)\n(rule "edge" (constraint edge_clearance (min 2mm)))\n')
    else:
        project = load(planned, "design/coupon.kicad_pro")
        project["board"]["design_settings"]["rules"]["min_copper_edge_clearance"] = 2.0
        save(planned, project, "design/coupon.kicad_pro")
    values = run_analysis(planned)
    assert values["drc"]["error"] == 0
    # The 20 x 10 mm board loses 2 mm at each edge, leaving a 16 x 6 mm rectangle.
    assert all(row["filled_area_mm2"] == pytest.approx(96, abs=0.05) for row in values["zone_refill"]["zones"])
    result = load(planned, RESULTS)
    if location == "custom_rules":
        assert "design/coupon.kicad_dru" in result["inputs"]
        assert "pcb/results/native/refill-rules.rpt" in result["outputs"]


def test_stale_saved_polygons_are_discarded_without_rewriting_original(work, tmp_path):
    root = tmp_path / "stale"
    prepare_reference(root)
    shutil.copyfile(work / "pcb/results/native/work/design/coupon.kicad_pcb", root / "design/coupon.kicad_pcb")
    def shrink(tree):
        for zone in children(tree, "zone"):
            for point in children(children(children(zone, "polygon")[0], "pts")[0], "xy"):
                if point[1] == 24:
                    point[1] = 22
    edit_board(root, shrink)
    original = (root / "design/coupon.kicad_pcb").read_bytes()
    assert b"(filled_polygon" in original
    values = run_analysis(root)
    assert all(row["filled_area_mm2"] == pytest.approx(128, abs=0.02) for row in values["zone_refill"]["zones"])
    assert (root / "design/coupon.kicad_pcb").read_bytes() == original
    filled = sexpdata.loads((root / "pcb/results/native/work/design/coupon.kicad_pcb").read_text())
    for zone in children(filled, "zone"):
        for polygon in children(zone, "filled_polygon"):
            assert max(point[1] for point in children(children(polygon, "pts")[0], "xy")) <= 22


def test_version_mismatch_fails_before_native_rewrite(planned, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    before = (planned / "design/coupon.kicad_pcb").read_bytes()
    command = native.steps(load(planned), output)[0][1]
    command[-1] = "9.0.0"
    result = subprocess.run(command, cwd=planned, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and "differs from kicad-cli" in result.stderr
    assert (planned / "design/coupon.kicad_pcb").read_bytes() == before
    assert not (output / "refill.json").exists()


def test_failed_bounds_retain_filled_board_and_native_findings(planned):
    plan = load(planned)
    plan["fabrication"]["drill_hits"]["pth"] = 3
    save(planned, plan)
    with pytest.raises(EvidenceError, match="expected exactly 3"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert result["status"] == "failed"
    assert "pcb/results/native/work/design/coupon.kicad_pcb" in result["outputs"]
    assert "pcb/results/native/refill.json" in result["outputs"]


def test_post_fill_disconnection_cannot_pass_from_an_old_saved_plane(work, tmp_path):
    root = tmp_path / "disconnected"
    prepare_reference(root)
    shutil.copyfile(work / "pcb/results/native/work/design/coupon.kicad_pcb", root / "design/coupon.kicad_pcb")
    def disconnect(tree):
        for zone in children(tree, "zone"):
            for point in children(children(children(zone, "polygon")[0], "pts")[0], "xy"):
                if point[1] == 24:
                    point[1] = 15
    edit_board(root, disconnect)
    original = (root / "design/coupon.kicad_pcb").read_bytes()
    with pytest.raises(EvidenceError, match="drc:.*acceptance limits"):
        run_analysis(root)
    assert load(root, "pcb/results/native/drc.json")["unconnected_items"]
    assert load(root, RESULTS)["status"] == "failed"
    assert (root / "design/coupon.kicad_pcb").read_bytes() == original
    assert (root / "pcb/results/native/work/design/coupon.kicad_pcb").is_file()


def test_empty_native_fill_is_not_invented_copper(planned):
    plan = load(planned)
    plan["checks"] = []
    save(planned, plan)
    def outside_outline(tree):
        for zone in children(tree, "zone"):
            for point in children(children(children(zone, "polygon")[0], "pts")[0], "xy"):
                point[1] += 30
    edit_board(planned, outside_outline)
    with pytest.raises(EvidenceError, match="drawn features below required"):
        run_analysis(planned)
    refill = load(planned, "pcb/results/native/refill.json")
    assert all(zone["filled_area_mm2"] == 0 for zone in refill["zones"])
    assert load(planned, RESULTS)["status"] == "failed"
