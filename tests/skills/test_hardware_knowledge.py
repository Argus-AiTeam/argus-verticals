from __future__ import annotations

import random
import re
import shutil
import subprocess
from itertools import combinations
from pathlib import Path

import pytest
from argus.core.pipeline_state import read_pipeline_state
from argus.skills.builtins import iter_vertical_skill_texts
from argus.skills.stage_machine import (
    StageCompletionError,
    advance_stage,
    complete_final_stage,
)
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.chip_design import stages as chip
from argus_verticals.digital_circuit import stages as digital

DIGITAL_SKILLS = Path(digital.__file__).parent / "skills" / "engineer"
CHIP_SKILLS = Path(chip.__file__).parent / "skills" / "engineer"


def _linked_guides(index: Path) -> list[Path]:
    links = re.findall(r"\]\(([^)]+\.md)\)", index.read_text(encoding="utf-8"))
    paths = [index.parent / link for link in links]
    assert all(path.is_file() for path in paths)
    return paths


def _examples() -> dict[str, str]:
    examples = {}
    for path in _linked_guides(DIGITAL_SKILLS / "digital-knowledge-map.md"):
        blocks = re.findall(r"```systemverilog\n(.*?)```", path.read_text(encoding="utf-8"), re.S)
        assert len(blocks) == 1, path
        examples[path.stem] = blocks[0]
    return examples


def _run(argv: list[str], root: Path) -> str:
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture
def examples(tmp_path):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus Verilog is required for executable RTL knowledge examples")
    blocks = _examples()
    source = tmp_path / "examples.sv"
    source.write_text("\n".join(blocks.values()), encoding="utf-8")
    _run(["iverilog", "-g2012", "-t", "null", str(source)], tmp_path)
    return source, blocks


def test_knowledge_maps_are_complete_linked_and_inherited():
    digital_guides = _linked_guides(DIGITAL_SKILLS / "digital-knowledge-map.md")
    chip_guides = _linked_guides(CHIP_SKILLS / "chip-architecture-map.md")
    assert len(digital_guides) == 12
    assert len(chip_guides) == 7
    inherited = dict(iter_vertical_skill_texts("chip_design"))
    for path in digital_guides + chip_guides:
        text = path.read_text(encoding="utf-8")
        assert len(text.split()) >= 180
        assert "description:" in text
        assert inherited[f"engineer/{path.name}"] == text
    assert "manager/chip-scope-selection.md" in inherited
    for name in ("digital-circuit-signoff-review.md", "chip-design-signoff-review.md"):
        assert "active workflow profile" in inherited[f"reviewer/{name}"]
    assert "Fixed-harness children" in inherited["engineer/digital-knowledge-map.md"]
    assert len(_examples()) == 12


@pytest.mark.parametrize("name, profile, expected", [
    ("digital_circuit", "rtl", ("specification", "rtl", "verification")),
    ("digital_circuit", "specification", ("specification",)),
    ("digital_circuit", "verification", ("verification",)),
    ("digital_circuit", "synthesis", ("verification", "synthesis")),
    ("chip_design", "architecture", ("definition", "architecture")),
    ("chip_design", "rtl", ("definition", "architecture", "environment", "rtl", "verification")),
    ("chip_design", "verification", ("verification",)),
    ("chip_design", "ppa", ("verification", "ppa")),
    ("chip_design", "prototype", ("verification", "ppa", "prototype")),
    ("chip_design", "benchmark", ("verification", "ppa", "benchmark")),
])
def test_hardware_profiles_use_only_declared_stages(tmp_path, name, profile, expected):
    persist_vertical(tmp_path, name, workflow_profile=profile)
    contract = load_vertical_contract(name, tmp_path)
    assert contract.stage_order == expected
    assert contract.workflow_mode == "staged"
    assert set(contract.checklist_items) == set(expected)
    assert contract.completion_issues(expected[-1], tmp_path, state_root=tmp_path)


@pytest.mark.parametrize("provider, name", [(digital, "digital_circuit"), (chip, "chip_design")])
@pytest.mark.parametrize("profile", [None, "full"])
def test_full_and_legacy_hardware_orders_are_preserved(tmp_path, provider, name, profile):
    persist_vertical(tmp_path, name, workflow_profile=profile)
    assert load_vertical_contract(name, tmp_path).stage_order == provider.STAGE_ORDER


def test_explicit_synthesis_task_cannot_use_legacy_not_applicable(tmp_path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis/NOT_APPLICABLE.md").write_text("No tools installed.")
    assert digital.stage_completion_issues("synthesis", tmp_path) == ()
    persist_vertical(tmp_path, "digital_circuit", workflow_profile="synthesis")
    contract = load_vertical_contract("digital_circuit", tmp_path)
    assert contract.completion_issues("synthesis", tmp_path, state_root=tmp_path)


@pytest.mark.parametrize("profile", ["rtl", "custom"])
def test_documented_rtl_profile_reaches_real_verified_completion(tmp_path, examples, profile):
    _source, blocks = examples
    state, work = tmp_path / "state", tmp_path / "work"
    for directory in ("design", "rtl", "tb", "verification"):
        (work / directory).mkdir(parents=True)
    persist_vertical(
        state, "digital_circuit", workflow_profile=profile,
        workflow_requested_stages=("rtl",) if profile == "custom" else None,
    )
    (work / "design/SPEC.md").write_text(
        "# Unsigned saturating adder\n"
        "Two unsigned 8-bit inputs, combinational min(a+b,255), carry flag iff a+b>255. "
        "Exhaustively check all 65536 pairs; no clocks, reset or backpressure.\n",
    )
    advance_stage(state, target_stage="rtl", reason="specification reviewed", evidence_root=work)
    rtl = work / "rtl/sat_add.sv"
    rtl.write_text(blocks["digital-arithmetic"])
    advance_stage(state, target_stage="verification", reason="RTL reviewed", evidence_root=work)
    with pytest.raises(StageCompletionError):
        complete_final_stage(state, reason="no execution yet", evidence_root=work)
    tb = work / "tb/sat_add_tb.sv"
    tb.write_text(blocks["digital-verification-formal"])
    executable = work / "verification/simulation"
    compile_argv = ["iverilog", "-g2012", "-s", "dc_sat_add8_tb", "-o", str(executable), str(rtl), str(tb)]
    _run(compile_argv, work)
    output = _run(["vvp", str(executable)], work)
    assert output.splitlines()[0] == "PASS: 65536 saturating-add cases"
    (work / "verification/simulation.log").write_text(output)
    complete_final_stage(state, reason="exhaustive oracle passed", evidence_root=work)
    assert vertical_completion_certificate_status(state, "digital_circuit")["ok"]
    final = read_pipeline_state(state)
    assert final["current_stage"] == "verification"
    assert set(final["stages"]) == {"specification", "rtl", "verification"}
    assert all(stage["status"] == "done" for stage in final["stages"].values())
    assert not (work / "synthesis").exists()
    assert not (work / ".argus/PIPELINE_STATE.json").exists()


@pytest.mark.parametrize("provider", [digital, chip])
def test_every_hardware_stage_combination_has_a_minimal_closed_scope(provider):
    from argus.core.vertical_contract import vertical_contract

    contract = vertical_contract("hardware", provider)
    for count in range(1, len(provider.STAGE_ORDER) + 1):
        for goals in combinations(provider.STAGE_ORDER, count):
            composed = contract.compose_workflow(goals)
            required = set(goals)
            while True:
                added = {dep for stage in required for dep in provider.WORKFLOW_STAGE_REQUIREMENTS[stage]}
                if added <= required:
                    break
                required.update(added)
            assert composed.stage_order == tuple(stage for stage in provider.STAGE_ORDER if stage in required)
            assert set(composed.checklist_items) == required
            assert composed.workflow_requested_stages == goals
            assert composed.completion_gate == contract.completion_gate


@pytest.mark.parametrize("goals, expected", [
    (("rtl", "ppa"), ("definition", "architecture", "environment", "rtl", "verification", "ppa")),
    (("architecture", "ppa"), ("definition", "architecture", "verification", "ppa")),
    (("environment",), ("environment",)),
    (("benchmark",), ("verification", "ppa", "benchmark")),
    (("signoff",), chip.STAGE_ORDER),
])
def test_chip_workflows_can_mix_studies_and_existing_design_work(tmp_path, goals, expected):
    persist_vertical(tmp_path, "chip_design", workflow_profile="custom", workflow_requested_stages=goals)
    assert load_vertical_contract("chip_design", tmp_path).stage_order == expected


def test_custom_verification_requires_the_design_not_only_a_testbench(tmp_path):
    (tmp_path / "tb").mkdir()
    (tmp_path / "tb/test.sv").write_text("module test; endmodule")
    (tmp_path / "verification").mkdir()
    (tmp_path / "verification/result.log").write_text("PASS")
    assert digital.stage_completion_issues("verification", tmp_path, workflow_profile="custom")


def test_custom_synthesis_is_real_work_not_legacy_not_applicable(tmp_path):
    (tmp_path / "synthesis").mkdir()
    (tmp_path / "synthesis/NOT_APPLICABLE.md").write_text("Legacy simulation-only task")
    assert digital.stage_completion_issues("synthesis", tmp_path) == ()
    assert digital.stage_completion_issues("synthesis", tmp_path, workflow_profile="custom")


def test_hardware_composition_menus_fit_manager_context_budget():
    from argus.manager._helpers import (
        _DEFAULT_FAST_ROUTE_MAX_PROMPT_CHARS,
        _DEFAULT_GROUNDED_ROUTE_MAX_PROMPT_CHARS,
    )
    from argus.roles.prompts.manager import (
        build_fast_vertical_decision_prompt,
        build_vertical_decision_prompt,
    )
    from argus.skills.vertical_select import available_vertical_purposes

    menu = available_vertical_purposes()
    for build, cap in [
        (build_fast_vertical_decision_prompt, _DEFAULT_FAST_ROUTE_MAX_PROMPT_CHARS),
        (build_vertical_decision_prompt, _DEFAULT_GROUNDED_ROUTE_MAX_PROMPT_CHARS),
    ]:
        prompt = build("Build RTL and measure PPA, without a prototype.", verticals_with_purpose=menu)
        assert "WORKFLOW_STAGES=" in prompt
        assert len(prompt) < cap


@pytest.mark.parametrize("module, capacity", [("dc_fifo4", 4), ("dc_elastic8", 1)])
def test_streaming_examples_against_independent_queue(tmp_path, examples, module, capacity):
    source, _blocks = examples
    rng = random.Random(3107)
    queue: list[int] = []
    rows = []
    for cycle in range(650):
        rst = int(cycle in {211, 489})
        valid = 1 if cycle < 12 else rng.randrange(2)
        ready = 0 if cycle < 12 else rng.randrange(2)
        data = rng.randrange(256)
        in_ready = int(len(queue) < capacity or (capacity == 1 and ready))
        out_valid = int(bool(queue))
        out_data = queue[0] if queue else 0
        rows.append(f"{rst} {valid} {ready} {data} {in_ready} {out_valid} {out_data}\n")
        if rst:
            queue.clear()
        else:
            if out_valid and ready:
                queue.pop(0)
            if valid and in_ready:
                queue.append(data)
    (tmp_path / "vectors.txt").write_text("".join(rows))
    tb = tmp_path / "stream_tb.sv"
    tb.write_text(f"""
module stream_tb;
    logic clk=0, rst=1, in_valid=0, out_ready=0;
    logic [7:0] in_data=0;
    wire in_ready, out_valid;
    wire [7:0] out_data;
    integer fd, count=0, rv, vv, rr, dd, er, ev, ed;
    {module} dut(clk, rst, in_valid, in_ready, in_data, out_valid, out_ready, out_data);
    initial begin
        #5; clk=1; #5; clk=0;
        fd=$fopen("vectors.txt","r");
        if (!fd) $fatal(1,"vectors missing");
        while ($fscanf(fd,"%d %d %d %d %d %d %d",rv,vv,rr,dd,er,ev,ed)==7) begin
            rst=rv; in_valid=vv; out_ready=rr; in_data=dd; #1;
            if (in_ready !== er[0] || out_valid !== ev[0]) $fatal(1,"control %0d",count);
            if (out_valid && out_data !== ed[7:0]) $fatal(1,"queue %0d",count);
            #4; clk=1; #5; clk=0; count=count+1;
        end
        if (count != 650) $fatal(1,"vector count");
        $display("PASS: 650 queue cycles"); $finish;
    end
endmodule
""")
    executable = tmp_path / "stream-sim"
    _run(["iverilog", "-g2012", "-s", "stream_tb", "-o", str(executable), str(source), str(tb)], tmp_path)
    assert _run(["vvp", str(executable)], tmp_path).splitlines()[0] == "PASS: 650 queue cycles"
