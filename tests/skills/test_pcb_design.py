from __future__ import annotations

import json
import shutil
from itertools import combinations
from pathlib import Path

import pytest
import sexpdata
from argus.skills.stage_machine import StageCompletionError, complete_final_stage, current_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.pcb_design import native, stages
from argus_verticals.pcb_design.design import PLAN, RESULTS, children, validate_plan
from argus_verticals.pcb_design.evidence import validate_verification
from argus_verticals.pcb_design.run_analysis import run_analysis
from argus_verticals.pcb_design.run_reference import prepare_reference, run_reference


def load(root, relative=PLAN):
    return json.loads((root / relative).read_text())


def save(root, value, relative=PLAN):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


def edit_expression(root, relative, mutate):
    path = root / relative
    tree = sexpdata.loads(path.read_text())
    mutate(tree)
    path.write_text(sexpdata.dumps(tree) + "\n")


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if shutil.which("kicad-cli") is None:
        pytest.skip("KiCad 9 is required for native PCB checks")
    root = tmp_path_factory.mktemp("pcb") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    root = Path(shutil.copytree(reference, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(reference), str(root)))
    return root


def test_real_native_reference_and_finite_completion(reference, tmp_path):
    values = validate_verification(reference)
    assert values["erc"] == values["drc"] == {"error": 0, "warning": 0, "exclusion": 0}
    assert values["drawn_features"] == {"F.Cu": 3, "B.Cu": 2, "F.Mask": 2, "B.Mask": 2, "Edge.Cuts": 4}
    assert values["drill_hits"] == {"pth": 2, "npth": 0}
    result = load(reference, RESULTS)
    assert result["kicad_version"] == native.version()
    assert [row["kind"] for row in result["commands"]] == ["erc", "drc", "gerbers", "drill"]
    assert len(result["inputs"]) == 8
    assert len(result["outputs"]) >= 9
    state = tmp_path / "state"
    persist_vertical(state, "pcb_design", workflow_profile="verification")
    complete_final_stage(state, reason="native checks independently replayed", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "pcb_design")["ok"]
    assert not (reference / "pcb/REVIEW.md").exists()


def test_relocated_test_fixture_is_valid_before_mutation(work):
    assert validate_verification(work)["drill_hits"]["pth"] == 2


@pytest.mark.parametrize("selection", ["erc", "drc", "parity", "fabrication"])
def test_only_selected_native_operations_are_required(planned, selection):
    plan = load(planned)
    plan["fabrication"] = None
    if selection == "erc":
        plan["checks"] = plan["checks"][:1]
        plan["design"]["board"] = "intentionally-not-selected.kicad_pcb"
    elif selection in ("drc", "parity"):
        plan["checks"] = plan["checks"][1:]
        plan["checks"][0]["schematic_parity"] = selection == "parity"
        if selection == "drc":
            plan["design"]["schematic"] = "intentionally-not-selected.kicad_sch"
    else:
        plan["fabrication"] = load(planned)["fabrication"]
        plan["checks"] = []
        plan["design"].pop("schematic")
    save(planned, plan)
    values = run_analysis(planned)
    expected = {"erc"} if selection == "erc" else {"drc"} if selection in ("drc", "parity") else {"drawn_features", "drill_hits"}
    assert set(values) == expected
    result = load(planned, RESULTS)
    if selection in ("erc", "drc", "fabrication"):
        omitted = "design/coupon.kicad_pcb" if selection == "erc" else "design/coupon.kicad_sch"
        assert omitted not in result["inputs"]


def test_workflow_scopes_and_early_requirements(planned):
    contract = load_vertical_contract("pcb_design")
    assert stages.VERTICAL_SKILL_PARENTS == ()
    for count in range(1, 5):
        for selected in combinations(stages.STAGE_ORDER, count):
            expected = set(selected) | ({"verification"} if "review" in selected else set())
            assert contract.compose_workflow(selected).stage_order == tuple(s for s in stages.STAGE_ORDER if s in expected)
    plan = load(planned)
    plan.pop("checks")
    plan.pop("fabrication")
    save(planned, plan)
    assert not stages.stage_completion_issues("design", planned)
    plan.pop("design")
    save(planned, plan)
    assert not stages.stage_completion_issues("specification", planned)
    assert stages.stage_completion_issues("verification", planned)


def test_review_and_missing_results_do_not_complete(work, tmp_path):
    assert stages.stage_completion_issues("review", work)
    (work / "pcb/REVIEW.md").write_text("Native checks and exports only; no physical qualification.\n")
    assert not stages.stage_completion_issues("review", work)
    state = tmp_path / "missing"
    persist_vertical(state, "pcb_design", workflow_profile="verification")
    with pytest.raises(StageCompletionError):
        complete_final_stage(state, reason="no native execution")


@pytest.mark.parametrize("mutation", ["thin_track", "unconnected", "parity", "erc"])
def test_deliberate_defects_are_reported_by_real_kicad(planned, mutation):
    plan = load(planned)
    plan["fabrication"] = None
    plan["checks"] = [plan["checks"][0 if mutation == "erc" else 1]]
    save(planned, plan)
    if mutation == "thin_track":
        def thin(tree):
            children(children(tree, "segment")[0], "width")[0][1] = 0.05
        edit_expression(planned, "design/coupon.kicad_pcb", thin)
    elif mutation == "unconnected":
        edit_expression(planned, "design/coupon.kicad_pcb", lambda tree: tree.remove(children(tree, "segment")[0]))
    elif mutation == "parity":
        def rename(tree):
            for net in children(tree, "net"):
                if net[2] == "/SIGNAL":
                    net[2] = "/WRONG"
        edit_expression(planned, "design/coupon.kicad_pcb", rename)
    else:
        edit_expression(planned, "design/coupon.kicad_sch", lambda tree: tree.remove(children(tree, "wire")[0]))
    with pytest.raises(EvidenceError, match="acceptance limits"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert result["status"] == "failed"
    assert result["commands"][0]["exit_code"] == 5
    report = load(planned, f"pcb/results/native/{'erc' if mutation == 'erc' else 'drc'}.json")
    if mutation == "unconnected":
        assert report["unconnected_items"]
    elif mutation == "parity":
        assert report["schematic_parity"]
    with pytest.raises(FileExistsError):
        run_analysis(planned)


def test_explicit_diagnostic_limits_retain_real_findings(planned):
    plan = load(planned)
    plan["checks"] = [{"kind": "drc", "max_errors": 1, "max_warnings": 0, "schematic_parity": False}]
    plan["fabrication"] = None
    save(planned, plan)
    edit_expression(planned, "design/coupon.kicad_pcb", lambda tree: tree.remove(children(tree, "segment")[0]))
    values = run_analysis(planned)
    assert values["drc"]["error"] == 1
    assert load(planned, RESULTS)["commands"][0]["exit_code"] == 5


@pytest.mark.parametrize("mutation", [
    "plan", "board", "library", "missing_snapshot", "hardlink_input", "self_copy",
    "failed", "version", "missing_command", "command", "cwd", "returncode", "missing_log",
    "missing_output", "changed_output", "hardlink_output", "missing_retained",
])
def test_stale_incomplete_or_fabricated_records_fail(work, mutation):
    result = load(work, RESULTS)
    if mutation in ("plan", "board", "library"):
        relative = {"plan": PLAN, "board": "design/coupon.kicad_pcb", "library": "design/local.pretty/Probe.kicad_mod"}[mutation]
        with (work / relative).open("a") as handle:
            handle.write("\n")
    elif mutation in ("missing_snapshot", "hardlink_input"):
        target = work / result["inputs"][PLAN]
        target.unlink()
        if mutation == "hardlink_input":
            target.hardlink_to(work / PLAN)
    elif mutation == "self_copy":
        result["inputs"][PLAN] = PLAN
    elif mutation == "failed":
        result["status"] = "failed"
    elif mutation == "version":
        result["kicad_version"] = "9.0.0"
    elif mutation == "missing_command":
        result["commands"].pop()
    elif mutation == "command":
        result["commands"][0]["command"].remove("--severity-all")
    elif mutation == "cwd":
        result["commands"][0]["cwd"] = "/elsewhere"
    elif mutation == "returncode":
        result["commands"][0]["exit_code"] = True
    elif mutation == "missing_log":
        Path(result["commands"][0]["log"]).unlink()
    else:
        source, retained = next(iter(result["outputs"].items()))
        if mutation == "missing_output":
            (work / source).unlink()
        elif mutation == "changed_output":
            (work / source).write_text("fabricated\n")
        else:
            (work / retained).unlink()
            if mutation == "hardlink_output":
                (work / retained).hardlink_to(work / source)
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        validate_verification(work)


@pytest.mark.parametrize("extension", [".gbr", ".drl"])
def test_matching_saved_copies_do_not_hide_wrong_native_geometry(work, extension):
    result = load(work, RESULTS)
    source = next(path for path in result["outputs"] if path.endswith(extension) and ("F_Cu" in path or "-PTH" in path))
    path = work / source
    data = path.read_text()
    before, after = ("X20000000", "X21000000") if extension == ".gbr" else ("X20.0", "X21.0")
    assert before in data
    path.write_text(data.replace(before, after))
    shutil.copyfile(path, work / result["outputs"][source])
    with pytest.raises(EvidenceError, match="geometry differs"):
        validate_verification(work)


def test_native_replay_catches_a_forged_clean_report_for_a_changed_design(work):
    edit_expression(work, "design/coupon.kicad_pcb", lambda tree: tree.remove(children(tree, "segment")[0]))
    result = load(work, RESULTS)
    shutil.copyfile(work / "design/coupon.kicad_pcb", work / result["inputs"]["design/coupon.kicad_pcb"])
    with pytest.raises(EvidenceError, match="native replay"):
        validate_verification(work)


@pytest.mark.parametrize("mutation", ["schema", "severities", "source", "excluded", "missing_group"])
def test_report_identity_and_all_finding_categories_are_required(work, mutation):
    result = load(work, RESULTS)
    source = "pcb/results/native/drc.json"
    report = load(work, source)
    if mutation == "schema":
        report["$schema"] = "invented"
    elif mutation == "severities":
        report["included_severities"] = ["error"]
    elif mutation == "source":
        report["source"] = "another.kicad_pcb"
    elif mutation == "excluded":
        report["violations"] = [{"severity": "exclusion", "type": "short", "description": "excluded", "items": []}]
    else:
        del report["unconnected_items"]
    save(work, report, source)
    shutil.copyfile(work / source, work / result["outputs"][source])
    with pytest.raises(EvidenceError):
        validate_verification(work)


@pytest.mark.parametrize("mutation", [
    "no_operations", "duplicate_check", "negative_bound", "bool_bound", "missing_parity",
    "missing_copper", "missing_outline", "unknown_layer", "wrong_holes",
    "wrong_stem", "external_library", "missing_library", "suppressed_rule", "exclusions",
    "variables", "zone", "slot", "empty_board", "malformed_board",
])
def test_unsupported_or_ambiguous_plan_and_design_fail_explicitly(planned, mutation):
    plan = load(planned)
    if mutation == "no_operations":
        plan["checks"], plan["fabrication"] = [], None
    elif mutation == "duplicate_check":
        plan["checks"] = [plan["checks"][0]] * 2
    elif mutation in ("negative_bound", "bool_bound"):
        plan["checks"][0]["max_errors"] = -1 if mutation == "negative_bound" else True
    elif mutation == "missing_parity":
        del plan["checks"][1]["schematic_parity"]
    elif mutation in ("missing_copper", "missing_outline"):
        del plan["fabrication"]["layers"]["B.Cu" if mutation == "missing_copper" else "Edge.Cuts"]
    elif mutation == "unknown_layer":
        plan["fabrication"]["layers"]["No.Such.Layer"] = 0
    elif mutation == "wrong_holes":
        plan["fabrication"]["drill_hits"] = {"pth": 2}
    elif mutation == "wrong_stem":
        plan["design"]["board"] = "design/other.kicad_pcb"
    elif mutation == "external_library":
        path = planned / "design/fp-lib-table"
        path.write_text(path.read_text().replace("${KIPRJMOD}/local.pretty", "/external/local.pretty"))
    elif mutation == "missing_library":
        (planned / "design/local.pretty/Probe.kicad_mod").unlink()
    elif mutation in ("suppressed_rule", "exclusions", "variables"):
        project = load(planned, "design/coupon.kicad_pro")
        if mutation == "suppressed_rule":
            project["board"]["design_settings"]["rule_severities"] = {"unconnected_items": "ignore"}
        elif mutation == "exclusions":
            project["board"]["design_settings"]["drc_exclusions"] = ["some finding"]
        else:
            project["text_variables"] = {"SUPPLY": "3V3"}
        save(planned, project, "design/coupon.kicad_pro")
    elif mutation == "zone":
        edit_expression(planned, "design/coupon.kicad_pcb", lambda tree: tree.append([sexpdata.Symbol("zone")]))
    elif mutation == "slot":
        def slot(tree):
            pad = children(children(tree, "footprint")[0], "pad")[0]
            children(pad, "drill")[0][1:] = [sexpdata.Symbol("oval"), 1, 2]
        edit_expression(planned, "design/coupon.kicad_pcb", slot)
    elif mutation == "empty_board":
        edit_expression(planned, "design/coupon.kicad_pcb", lambda tree: tree.__setitem__(slice(None), [node for node in tree if node not in children(tree, "footprint")]))
    else:
        (planned / "design/coupon.kicad_pcb").write_text("(not_a_board)\n")
    save(planned, plan)
    with pytest.raises(EvidenceError):
        validate_plan(planned)


def test_hierarchical_dependency_closure_and_cycle_rejection(planned):
    plan = load(planned)
    plan["checks"] = plan["checks"][:1]
    plan["fabrication"] = None
    save(planned, plan)
    child = planned / "design/sub/child.kicad_sch"
    child.parent.mkdir()
    child.write_text('(kicad_sch (version 20250114))\n')
    def sheet(tree):
        tree.append([sexpdata.Symbol("sheet"), [sexpdata.Symbol("property"), "Sheetfile", "sub/child.kicad_sch"]])
    edit_expression(planned, "design/coupon.kicad_sch", sheet)
    _, inputs = validate_plan(planned)
    assert "design/sub/child.kicad_sch" in inputs
    child.write_text('(kicad_sch (sheet (property "Sheetfile" "${KIPRJMOD}/coupon.kicad_sch")))\n')
    with pytest.raises(EvidenceError, match="cyclic"):
        validate_plan(planned)


def test_read_only_checker_preserves_project_bytes(reference):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    validate_verification(reference)
    after = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    assert after == before


def test_tool_unavailability_is_explicit(planned, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(EvidenceError, match="KiCad 9 CLI is required"):
        run_analysis(planned)
    assert not (planned / RESULTS).exists()


def test_all_real_role_builders_receive_the_canonical_contract(tmp_path):
    from argus.roles.prompts import resolve_role_prompt
    from argus.roles.prompts.engineer import mission_request
    from argus.roles.prompts.manager import stage_decision_request
    from argus.roles.prompts.planner import PLAN_PREVIEW, continuous_request
    from argus.roles.prompts.reviewer import evaluate_request

    state, project = tmp_path / "state", tmp_path / "project"
    project.mkdir()
    persist_vertical(state, "pcb_design", workflow_profile="verification")
    requests = [
        stage_decision_request(state, stage=current_stage(state)),
        continuous_request(state, operation=PLAN_PREVIEW, altitude_root=project, include_search_altitude=False),
        mission_request(state, altitude_root=project, stage=current_stage(state)),
        evaluate_request(state, altitude_root=project),
    ]
    canonical = Path(stages.__file__).with_name("evidence-contract.md").read_text()
    for request in requests:
        prompt = resolve_role_prompt(request)
        assert prompt.stage_order == ("verification",)
        assert canonical in prompt.role_banner
        assert stages.evidence_check_command("pcb_design", "verification") in prompt.role_banner
