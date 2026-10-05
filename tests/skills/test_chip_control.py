from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from argus.skills.stage_machine import complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.chip_design import control, control_model, control_simulation, stages
from argus_verticals.chip_design.run_control_reference import prepare_reference, run_reference
from argus_verticals.hardware.shared.evidence import EvidenceError


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if any(shutil.which(tool) is None for tool in ("yosys", "iverilog", "vvp")):
        pytest.skip("native Yosys and Icarus Verilog required")
    root = tmp_path_factory.mktemp("control") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    return Path(shutil.copytree(reference, tmp_path / "work"))


@pytest.fixture
def fresh(reference, tmp_path):
    root = tmp_path / "fresh"
    prepare_reference(root)
    return root


def change_spec(root, **values):
    path = root / "design/control-spec.json"
    spec = json.loads(path.read_text())
    spec.update(values)
    path.write_text(json.dumps(spec))
    return spec


def retain(root, relative):
    result = json.loads((root / control.RESULTS).read_text())
    shutil.copyfile(root / relative, root / result["outputs"][relative])


def test_native_reference_and_read_only_profile_completion(reference, tmp_path):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    result = control.validate(reference)
    assert result["task_accepted"] and result["status"] == "passed"
    for row in result["configurations"].values():
        native = row["synthesis"]
        assert 0 < native["generic_cells"] <= 2000
        assert native["headroom_cells"] == 2000 - native["generic_cells"]
        for sim in row["simulations"].values():
            assert sim["passed"] and sim["samples"] > 400
            assert sim["coverage"]["write_strobes"] == list(range(16))
            assert all(c["comparisons"] > 0 and c["mismatches"] == 0 for c in sim["checks"].values())
    state = tmp_path / "state"
    persist_vertical(state, "chip_design", workflow_profile="control")
    complete_final_stage(state, reason="independent control review", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "chip_design")["ok"]
    assert load_vertical_contract("chip_design", state).stage_order == ("verification",)
    assert not (reference / "design/MEMORY_MODEL.json").exists()
    command = subprocess.run(shlex.split(stages.control_check_command()), cwd=reference, capture_output=True, text=True, timeout=60)
    assert command.returncode == 0 and command.stdout.strip() == "[]", command.stdout + command.stderr
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


MUTATIONS = [
    ("strobes", "scratch <= (scratch & ~write_mask) | (PWDATA & write_mask)", "scratch <= PWDATA"),
    ("irq_clear_priority", "(pending && !clear_irq) || event_tick", "(pending || event_tick) && !clear_irq"),
    ("early_write", "complete && PWRITE && !PSLVERR", "PRESETn && PSEL && PWRITE && !PSLVERR"),
    ("zero_wait", "(wait_count == WAIT_CYCLES)", "1'b1"),
    ("address_alias", "PADDR - BASE_ADDR", "(PADDR - BASE_ADDR) & 32'hff"),
    ("no_error", "complete && (!mapped || (PWRITE && offset == 8))", "1'b0"),
    ("timer_early", "control[0] && (count == 0)", "control[0] && (count == 1)"),
    ("irq_mask", "assign IRQ = pending && irq_mask", "assign IRQ = pending"),
    ("reset_scratch", "scratch <= 0", "scratch <= 1"),
    ("synchronous_reset", "posedge PCLK or negedge PRESETn", "posedge PCLK"),
]


@pytest.mark.parametrize("name,old,new", MUTATIONS)
def test_actual_rtl_mutations_are_detected_in_both_models(fresh, name, old, new):
    source = fresh / "rtl/control_reference.sv"
    text = source.read_text()
    assert old in text
    source.write_text(text.replace(old, new))
    change_spec(fresh, goal="diagnose")
    result = control.run(fresh)
    assert result["conclusion_valid"] and result["task_accepted"] and result["status"] == "failed"
    for model in ("rtl", "synth"):
        assert any(not c["simulations"][model]["passed"] for c in result["configurations"].values()), name
    assert control.validate(fresh) == result


def test_design_failure_preserves_evidence_and_does_not_complete(fresh):
    change_spec(fresh, max_generic_cells=1)
    with pytest.raises(EvidenceError, match="original behavior or generic-cell"):
        control.run(fresh)
    assert json.loads((fresh / control.RESULTS).read_text())["status"] == "failed"
    result = json.loads((fresh / control.ASSESSMENT).read_text())
    assert not result["task_accepted"] and result["conclusion_valid"]
    assert all(c["simulations"]["rtl"]["passed"] for c in result["configurations"].values())
    assert stages.stage_completion_issues("verification", fresh, workflow_profile="control")
    with pytest.raises(FileExistsError):
        control.run(fresh)


def test_generic_cell_limit_is_inclusive(reference, fresh):
    previous = json.loads((reference / control.ASSESSMENT).read_text())
    bound = max(c["synthesis"]["generic_cells"] for c in previous["configurations"].values())
    change_spec(fresh, max_generic_cells=bound)
    result = control.run(fresh)
    assert result["status"] == "passed"
    assert min(c["synthesis"]["headroom_cells"] for c in result["configurations"].values()) == 0


@pytest.mark.parametrize("field,value", [
    ("goal", "repair_without_passing"), ("contract", "arbitrary_apb"), ("base_address", 3),
    ("base_address", True), ("base_address", 0x100000000), ("max_generic_cells", 0),
    ("max_generic_cells", 20000.0), ("configurations", {}), ("sources", ["../outside.sv"]),
    ("limitations", []), ("top", "not a name"), ("extra", 1),
])
def test_original_schema_rejects_unsupported_requests(fresh, field, value):
    change_spec(fresh, **{field: value})
    with pytest.raises(EvidenceError):
        control.run(fresh)
    assert not (fresh / control.DIRECTORY).exists()


@pytest.mark.parametrize("field,value", [
    ("counter_width", 3), ("counter_width", 33), ("counter_width", False),
    ("wait_cycles", -1), ("wait_cycles", 4), ("seed", 0), ("seed", 1.0),
])
def test_configuration_bounds(fresh, field, value):
    spec = change_spec(fresh)
    spec["configurations"]["compact"][field] = value
    change_spec(fresh, configurations=spec["configurations"])
    with pytest.raises(EvidenceError):
        control_model.resolve(fresh)


@pytest.mark.parametrize("text", ['`include "other.sv"', 'initial $readmemh("data", memory);', "`define ALTER 1"])
def test_external_simulation_inputs_are_rejected(fresh, text):
    path = fresh / "rtl/control_reference.sv"
    path.write_text(path.read_text() + "\n" + text)
    with pytest.raises(EvidenceError, match="external data"):
        control_model.resolve(fresh)


@pytest.mark.parametrize("tamper", ["source", "spec", "command", "trace", "stats", "netlist", "bench", "assessment"])
def test_forged_or_stale_evidence_is_rejected(work, tamper):
    result = json.loads((work / control.RESULTS).read_text())
    if tamper == "source":
        source = work / "rtl/control_reference.sv"
        source.write_text(source.read_text() + "\n// changed input\n")
    elif tamper == "spec":
        change_spec(work, max_generic_cells=1900)
    elif tamper == "command":
        result["commands"][0]["command"].append("invented")
        (work / control.RESULTS).write_text(json.dumps(result))
    else:
        relative = {
            "trace": f"{control.DIRECTORY}/compact.rtl.simulate.log",
            "stats": f"{control.DIRECTORY}/compact.stats.json",
            "netlist": f"{control.DIRECTORY}/compact.netlist.json",
            "bench": f"{control.DIRECTORY}/compact.rtl.tb.sv",
            "assessment": control.ASSESSMENT,
        }[tamper]
        path = work / relative
        if tamper == "trace":
            path.write_text(path.read_text().replace("END CONTROL", "missing terminator"))
        elif tamper == "bench":
            path.write_text(path.read_text() + "\n// changed generated bench\n")
        else:
            value = json.loads(path.read_text())
            if tamper == "stats":
                value["modules"]["\\control_reference"]["num_cells"] = 1
            elif tamper == "netlist":
                value["modules"]["control_reference"]["cells"] = []
            else:
                value["configurations"]["compact"]["synthesis"]["generic_cells"] = 1
            path.write_text(json.dumps(value))
        retain(work, relative)
    with pytest.raises(EvidenceError):
        control.validate(work)


def test_native_failure_is_not_negative_diagnosis(fresh, monkeypatch):
    change_spec(fresh, goal="diagnose")
    monkeypatch.setattr(control, "commands", lambda spec: [("probe", [sys.executable, "-c", "print('native failure'); raise SystemExit(9)"])])
    with pytest.raises(EvidenceError, match="exited 9"):
        control.run(fresh)
    result = json.loads((fresh / control.RESULTS).read_text())
    assert result["status"] == "failed" and result["commands"][0]["exit_code"] == 9
    assert not (fresh / control.ASSESSMENT).exists()


def test_timeout_retains_actual_exit(fresh, monkeypatch):
    monkeypatch.setattr(control, "COMMAND_TIMEOUT", 0.1)
    monkeypatch.setattr(control, "commands", lambda spec: [("probe", [sys.executable, "-c", "import time; time.sleep(3)"])])
    with pytest.raises(EvidenceError, match="seconds"):
        control.run(fresh)
    row = json.loads((fresh / control.RESULTS).read_text())["commands"][0]
    assert row["exit_code"] != 0 and "seconds" in row["stop_reason"]


@pytest.mark.parametrize("width,wait", [(4, 0), (32, 3)])
def test_native_parameter_extremes(fresh, width, wait):
    change_spec(fresh, configurations={
        "boundary": {"counter_width": width, "wait_cycles": wait, "seed": 11},
        "other": {"counter_width": 9, "wait_cycles": 1, "seed": 13},
    }, base_address=0xFFFFFF00)
    assert control.run(fresh)["status"] == "passed"


def test_model_hand_calculated_expiry_and_set_clear_priority():
    spec = {"base_address": 0}
    config = {"counter_width": 4, "wait_cycles": 0}
    idle = {"reset": 1, "select": 0, "enable": 0, "write": 0, "address": 0, "data": 0, "strobes": 0}
    def write(address, data):
        return {**idle, "select": 1, "enable": 1, "write": 1, "address": address, "data": data, "strobes": 1}
    frames = [{**idle, "reset": 0}, write(16, 1), write(4, 1), write(0, 1), idle, idle, write(12, 1)]
    result = control_model.expected(spec, config, frames)
    assert [r["irq_after"] for r in result] == [0, 0, 0, 0, 0, 1, 0]
    frames += [write(4, 0), write(0, 3), write(12, 1)]
    assert control_model.expected(spec, config, frames)[-1]["irq_after"] == 1


def test_stimulus_is_legal_and_exercises_stable_waits(reference):
    spec, _ = control_model.resolve(reference)
    for config in spec["configurations"].values():
        frames = control_simulation.stimulus(spec, config)
        for index, frame in enumerate(frames):
            if frame["reset"] and frame["select"] and frame["enable"]:
                previous = frames[index - 1]
                assert previous["select"] and previous["reset"]
                assert all(frame[k] == previous[k] for k in ("write", "address", "data", "strobes", "protection"))
        assert {f["protection"] for f in frames} == set(range(8))


@pytest.mark.parametrize("role,operation", [("manager", "stage_decision"), ("planner", "plan_preview"), ("engineer", "mission"), ("reviewer", "evaluate")])
def test_control_roles_receive_exact_original_contract(tmp_path, role, operation):
    from argus.roles.prompts import ChecklistMode, RoleName, RolePromptRequest, resolve_role_prompt

    persist_vertical(tmp_path, "chip_design", workflow_profile="control")
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=tmp_path,
        stage="verification", checklist_mode=ChecklistMode.STAGE,
    ))
    assert prompt.stage_order == ("verification",)
    assert Path(stages.__file__).with_name("control-contract.md").read_text() in prompt.role_banner
    assert stages.control_check_command() in prompt.role_banner
    assert "Design/repair must pass" in prompt.role_banner
    assert "your read/search-only tools need no shell permission" in prompt.role_banner
    assert "Missing or failed host evidence remains incomplete" in prompt.role_banner
    assert stages.WORKFLOW_PROFILES["full"]["stages"] == stages.STAGE_ORDER
    assert len(stages.STAGE_ORDER) == 9


def test_classifier_visible_purpose_explains_self_contained_control_scope():
    from argus.skills.vertical_select import available_vertical_purposes

    purpose = available_vertical_purposes()["chip_design"]
    assert "apb4-timer-v1" in purpose
    assert "control profile already includes authorized RTL repair" in purpose
    assert "generic counts are not PPA" in purpose
    assert "do not require custom rtl+ppa stages" in purpose


def test_host_replays_control_evidence_before_read_only_review(reference, tmp_path):
    from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence
    from argus.life.context_packet import create_mission_context

    state = tmp_path / "state"
    persist_vertical(state, "chip_design", workflow_profile="control")
    packet = create_mission_context(
        life_dir=state, mission_id="control", stage="verification", objective="Verify original control inputs",
    )
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    evidence = collect_round_evidence(RoundEvidenceRequest(reference, packet.parent, 1))
    control_evidence = [e for e in evidence if e.provider.startswith("argus_verticals.chip_design.")]
    assert len(control_evidence) == 1
    assert not any(e.provider.startswith("argus_verticals.hardware.shared.review:") for e in evidence)
    assert "Host-executed control completion check" in control_evidence[0].reviewer_text
    assert '"issues": []' in control_evidence[0].reviewer_text
    assert '"engineering_status": "passed"' in control_evidence[0].reviewer_text
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


@pytest.mark.parametrize("profile", ["", "verification", "full"])
def test_host_control_evidence_ignores_legacy_profiles(work, tmp_path, monkeypatch, profile):
    from argus.core.pipeline_state import write_pipeline_state
    from argus.engineer.round_evidence import RoundEvidenceRequest

    from argus_verticals.chip_design import control_report

    state = tmp_path / "state"
    write_pipeline_state(state, {"vertical": "chip_design", "workflow_profile": profile})
    monkeypatch.setattr(control_report, "validate_completion", lambda _: pytest.fail("legacy profile replayed control"))
    assert control_report.round_evidence(RoundEvidenceRequest(work, state / "handoffs/task", 1)) is None


@pytest.mark.parametrize("failure", ["missing_report", "os_error"])
def test_host_control_failures_are_evidence_not_success(work, tmp_path, monkeypatch, failure):
    from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence

    from argus_verticals.chip_design import control_report

    state = tmp_path / "state"
    persist_vertical(state, "chip_design", workflow_profile="control")
    if failure == "missing_report":
        (work / control_report.REPORT).unlink()
    else:
        def unavailable(_):
            raise OSError("native evidence unavailable")
        monkeypatch.setattr(control_report, "validate_completion", unavailable)
    evidence = collect_round_evidence(RoundEvidenceRequest(work, state / "handoffs/task", 1))
    item, = [e for e in evidence if e.provider.startswith("argus_verticals.chip_design.")]
    assert "Control completion check failed:" in item.reviewer_text
    assert item.engineer_note in item.reviewer_text
    assert '"issues": []' not in item.reviewer_text


@pytest.mark.parametrize("report", [None, "", "TODO", "## Scope\nOriginal inputs.\n## Findings and changes\nNo changes.\n## Evidence\n```json\n{}\n```\n## Limitations\nFinite checks only.\n"])
def test_final_completion_rejects_missing_or_incomplete_report(work, report):
    path = work / "verification/CONTROL_REVIEW.md"
    if path.exists():
        path.unlink()
    if report is not None:
        path.write_text(report)
    issues = stages.stage_completion_issues("verification", work, workflow_profile="control")
    assert issues and "CONTROL_REVIEW.md" in " ".join(issues)


def _perfect_trace(spec, config, frames):
    lines = []
    for index, row in enumerate(control_model.expected(spec, config, frames)):
        lines.append(
            f"SAMPLE {index} {row.get('ready', 0)} {row.get('error', 0)} "
            f"{row.get('read_data', 0):08x} {row['irq_before']} {row['irq_after']}"
        )
    return "\n".join([*lines, "END CONTROL", ""])


def test_idle_label_cannot_prove_semantic_coverage():
    spec, config = {"base_address": 0}, {"counter_width": 8, "wait_cycles": 0, "seed": 1}
    frame = {
        "case": "set_dominates_clear", "reset": 1, "select": 0, "enable": 0,
        "write": 0, "address": 0, "data": 0, "strobes": 0, "protection": 0,
    }
    with pytest.raises(EvidenceError, match="semantic coverage"):
        control_simulation.measure(spec, config, [frame], _perfect_trace(spec, config, [frame]))


def test_unselected_writes_do_not_cover_strobes(reference):
    spec, _ = control_model.resolve(reference)
    config = spec["configurations"]["compact"]
    frames = control_simulation.stimulus(spec, config)
    for frame in frames:
        if frame["write"] and frame["strobes"] == 4 and frame["address"] == spec["base_address"] + 20:
            frame["select"] = 0
    with pytest.raises(EvidenceError, match="semantic coverage"):
        control_simulation.measure(spec, config, frames, _perfect_trace(spec, config, frames))


def test_coverage_counts_real_reference_events_not_case_names(reference):
    spec, _ = control_model.resolve(reference)
    for config in spec["configurations"].values():
        frames = control_simulation.stimulus(spec, config)
        for frame in frames:
            frame["case"] = "arbitrary_label"
        result = control_simulation.measure(spec, config, frames, _perfect_trace(spec, config, frames))
        coverage = result["coverage"]
        assert result["passed"] and coverage["cases"] == ["arbitrary_label"]
        for event, count in coverage["reference_event_counts"].items():
            if event == "wait_observations" and config["wait_cycles"] == 0:
                assert count == 0 and coverage["first_event_cycles"][event] == []
            else:
                assert count > 0 and len(coverage["first_event_cycles"][event]) == min(count, 4)
                assert all(0 <= cycle < len(frames) for cycle in coverage["first_event_cycles"][event])
        for register in ("scratch", "reload"):
            assert coverage["completed_write_strobes"][register] == list(range(16))
            for strobe, cycle in coverage["first_strobe_cycles"][register].items():
                frame = frames[cycle]
                assert frame["write"] and frame["select"] and frame["enable"]
                assert frame["strobes"] == int(strobe)
                assert frame["address"] == spec["base_address"] + control_model.REGISTERS[register]


def test_reference_event_counts_follow_hand_calculated_state():
    idle = {"reset": 1, "select": 0, "enable": 0, "write": 0, "address": 0, "data": 0, "strobes": 0}
    def write(address, data):
        return {**idle, "select": 1, "enable": 1, "write": 1, "address": address, "data": data, "strobes": 1}
    frames = [{**idle, "reset": 0}, write(16, 1), write(4, 1), write(0, 1), idle, idle,
              write(12, 1), write(4, 0), write(0, 3), write(12, 1), {**idle, "reset": 0}]
    rows, coverage = control_model.reference_trace({"base_address": 0}, {"counter_width": 4, "wait_cycles": 0}, frames)
    for name, cycle in (("one_shot_expiries", 5), ("periodic_expiries", 9), ("zero_reload_expiries", 9),
                        ("set_clear_races", 9), ("async_active_irq_resets", 10)):
        assert coverage["reference_event_counts"][name] == 1
        assert coverage["first_event_cycles"][name] == [cycle]
    assert rows[9]["irq_after"] == 1 and rows[10]["irq_before"] == 0


@pytest.mark.parametrize("goal", ["design", "diagnose"])
def test_missing_coverage_is_not_an_engineering_diagnosis(fresh, monkeypatch, goal):
    change_spec(fresh, goal=goal)
    def idle_only(spec, config):
        return [{
            "case": "set_dominates_clear", "reset": 0, "select": 0, "enable": 0,
            "write": 0, "address": 0, "data": 0, "strobes": 0, "protection": 0,
        }]
    monkeypatch.setattr(control_simulation, "stimulus", idle_only)
    with pytest.raises(EvidenceError, match="semantic coverage"):
        control.run(fresh)
    result = json.loads((fresh / control.RESULTS).read_text())
    assert result["status"] == "failed" and all(row["exit_code"] == 0 for row in result["commands"])
    assert not (fresh / control.ASSESSMENT).exists()


@pytest.mark.parametrize("field", ["reference_event_counts", "first_event_cycles", "first_strobe_cycles"])
def test_coverage_witness_tampering_is_rejected(work, field):
    path = work / control.ASSESSMENT
    result = json.loads(path.read_text())
    coverage = result["configurations"]["compact"]["simulations"]["rtl"]["coverage"]
    if field == "reference_event_counts":
        coverage[field]["set_clear_races"] += 1
    elif field == "first_event_cycles":
        coverage[field]["set_clear_races"][0] += 1
    else:
        coverage[field]["scratch"]["0"] += 1
    path.write_text(json.dumps(result))
    retain(work, control.ASSESSMENT)
    with pytest.raises(EvidenceError, match="assessment"):
        control.validate(work)


@pytest.mark.parametrize("tamper", [
    "goal", "parameter", "missing_configuration", "cell_count", "comparison", "coverage",
    "duplicate_key", "numeric_type", "nonfinite",
])
def test_report_summary_must_match_replayed_original_facts(work, monkeypatch, tamper):
    from argus_verticals.chip_design import control_report

    measured = json.loads((work / control.ASSESSMENT).read_text())
    monkeypatch.setattr(control, "validate", lambda root: measured)
    path = work / control_report.REPORT
    text = path.read_text()
    prefix, tail = text.split("```json\n", 1)
    payload, suffix = tail.split("\n```", 1)
    data = json.loads(payload)
    if tamper == "goal":
        data["goal"] = "diagnose"
    elif tamper == "parameter":
        data["configurations"]["compact"]["parameters"]["counter_width"] += 1
    elif tamper == "missing_configuration":
        data["configurations"].pop("compact")
    elif tamper == "cell_count":
        data["configurations"]["compact"]["generic_cells"] -= 1
    elif tamper == "comparison":
        data["configurations"]["compact"]["simulations"]["rtl"]["mismatches"] += 1
    elif tamper == "coverage":
        data["configurations"]["compact"]["simulations"]["rtl"]["reference_event_counts"]["set_clear_races"] += 1
    elif tamper == "numeric_type":
        data["configurations"]["compact"]["parameters"]["seed"] = 1.0
    elif tamper == "nonfinite":
        data["base_address"] = float("nan")
    payload = json.dumps(data, indent=2)
    if tamper == "duplicate_key":
        payload = payload.replace('"goal": "design"', '"goal": "design", "goal": "design"')
    path.write_text(prefix + "```json\n" + payload + "\n```" + suffix)
    with pytest.raises(EvidenceError, match="CONTROL_REVIEW.md"):
        control_report.validate_completion(work)


@pytest.mark.parametrize("tamper", ["missing", "only_code", "duplicate_heading", "heading_in_code", "encoding", "oversized"])
def test_report_structure_fails_before_expensive_native_replay(work, monkeypatch, tamper):
    from argus_verticals.chip_design import control_report

    def unexpected(root):
        raise AssertionError("native replay must not run for a missing/incomplete report")
    monkeypatch.setattr(control, "validate", unexpected)
    path = work / control_report.REPORT
    text = path.read_text()
    if tamper == "missing":
        path.unlink()
    elif tamper == "only_code":
        path.write_text(text.replace("## Scope\n", "## Scope\n```text\n").replace("\n\n## Findings", "\n```\n\n## Findings"))
    elif tamper == "duplicate_heading":
        path.write_text(text + "\n## Scope\nDuplicate.\n")
    elif tamper == "heading_in_code":
        path.write_text(text.replace("## Scope\n", "```text\n## Scope\n").replace("\n\n## Findings", "\n```\n\n## Findings"))
    elif tamper == "encoding":
        path.write_bytes(b"\xff")
    else:
        path.write_text(text + " " * 65536)
    with pytest.raises(EvidenceError, match="CONTROL_REVIEW.md"):
        control_report.validate_completion(work)


def test_report_cannot_change_during_native_replay(work, monkeypatch):
    from argus_verticals.chip_design import control_report

    path = work / control_report.REPORT
    def change_report(root):
        path.write_text(path.read_text() + "\nConcurrent edit.\n")
        return json.loads((work / control.ASSESSMENT).read_text())
    monkeypatch.setattr(control, "validate", change_report)
    with pytest.raises(EvidenceError, match="changed during"):
        control_report.validate_completion(work)


def test_negative_diagnosis_can_complete_with_truthful_report(fresh):
    from argus.engineer.round_evidence import RoundEvidenceRequest

    from argus_verticals.chip_design import control_report
    from argus_verticals.chip_design.run_control_reference import write_reference_report

    change_spec(fresh, goal="diagnose", max_generic_cells=1)
    measured = control.run(fresh)
    assert measured["status"] == "failed" and measured["task_accepted"]
    write_reference_report(fresh)
    assert control_report.validate_completion(fresh) == measured
    persist_vertical(fresh, "chip_design", workflow_profile="control")
    host = control_report.round_evidence(RoundEvidenceRequest(fresh, fresh / ".argus/life", 1))
    assert '"issues": []' in host.reviewer_text and '"engineering_status": "failed"' in host.reviewer_text
    path = fresh / control_report.REPORT
    path.write_text(path.read_text().replace('"engineering_status": "failed"', '"engineering_status": "passed"'))
    assert stages.stage_completion_issues("verification", fresh, workflow_profile="control")
