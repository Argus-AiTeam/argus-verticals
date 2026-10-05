from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.power_electronics import native, stages, validation
from argus_verticals.power_electronics.model import PLAN, RESULTS
from argus_verticals.power_electronics.robustness import ASSESSMENT
from argus_verticals.power_electronics.run_analysis import run_analysis
from argus_verticals.power_electronics.run_robustness_reference import prepare_reference


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if shutil.which("ngspice") is None:
        pytest.skip("native ngspice is required")
    root = tmp_path_factory.mktemp("power-validation") / "reference"
    prepare_reference(root)
    spec = json.loads((root / "design/operating.json").read_text())
    spec["axes"] = spec["axes"][:1]
    (root / "design/operating.json").write_text(json.dumps(spec))
    run_analysis(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    root = Path(shutil.copytree(reference, tmp_path / "project"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(reference), str(root)))
    return root


def test_native_validation_reused_across_stages_and_processes(work, tmp_path, monkeypatch):
    from argus.core.pipeline_state import read_pipeline_state
    from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence
    from argus.skills.vertical_select import persist_vertical

    state = tmp_path / "state"
    persist_vertical(state, "power_electronics", workflow_profile="simulation")
    selected = read_pipeline_state(state)
    calls = []
    execute = native.execute

    def counted(*args, **kwargs):
        calls.append(args[1]["id"])
        return execute(*args, **kwargs)

    monkeypatch.setattr(native, "execute", counted)
    gathered = collect_round_evidence(RoundEvidenceRequest(work, state / "handoffs/task", 1))
    host, = [item for item in gathered if item.provider.startswith("argus_verticals.hardware.shared.review:")]
    assert '"issues": []' in host.reviewer_text
    assert read_pipeline_state(state) == selected
    assert (state / "power-validation/implementation/shared/native.py").is_file()
    assert len(calls) == 6
    report = work / "power/REVIEW.md"
    report.write_text("Complete finite diagnosis; no hardware qualification.")
    assert not stages.stage_completion_issues("review", work, state_root=state)
    report.write_text("Clarified: modeled losses are not measured hardware efficiency.")
    assert not stages.stage_completion_issues("review", work, state_root=state)
    assert len(calls) == 6
    script = """
from pathlib import Path
from argus_verticals.power_electronics import native, stages
def no_replay(*args, **kwargs):
    raise AssertionError('unchanged numerical evidence was replayed')
native.execute = no_replay
assert not stages.stage_completion_issues('review', Path.cwd())
print('unchanged native agreement reused')
"""
    env = {**os.environ, "ARGUS_SKILL_SESSION_ROOT": str(state)}
    result = subprocess.run([sys.executable, "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "unchanged native agreement reused" in result.stdout
    report.unlink()
    assert stages.stage_completion_issues("review", work, state_root=state)
    model = work / "design/buck.json"
    original = model.read_bytes()
    model.write_bytes(original + b" ")
    issues = stages.stage_completion_issues("simulation", work, state_root=state)
    assert issues and "changed file" in issues[0]
    assert (state / "power-validation/project/design/buck.json").read_bytes() == original


@pytest.fixture
def unit_cache(work, tmp_path, monkeypatch):
    # Only the snapshot/reuse algorithm is stubbed here; the test above uses real native replay.
    state = tmp_path / "state"
    calls = []
    monkeypatch.setattr(validation, "validate_simulation", lambda root: calls.append(root))
    validation.validate_current(work, state_root=state)
    assert len(calls) == 1
    return work, state, calls


@pytest.mark.parametrize("relative", [
    PLAN, RESULTS, ASSESSMENT, "design/buck.json", "design/operating.json",
    "power/results/native/nominal_coarse/wave.raw",
    "power/results/retained/nominal_coarse/wave.raw",
    "power/results/inputs/design/operating.json",
])
def test_every_numerical_byte_change_requires_validation(unit_cache, relative):
    root, state, calls = unit_cache
    path = root / relative
    path.write_bytes(path.read_bytes() + b" ")
    validation.validate_current(root, state_root=state)
    assert len(calls) == 2


def test_same_size_and_timestamp_cannot_hide_changed_native_copies(unit_cache):
    root, state, calls = unit_cache
    for folder in ("native", "retained"):
        path = root / f"power/results/{folder}/nominal_coarse/wave.raw"
        stat = path.stat()
        data = path.read_bytes()
        path.write_bytes(data.replace(b"e-03", b"e-02", 1))
        assert path.read_bytes() != data and path.stat().st_size == stat.st_size
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    validation.validate_current(root, state_root=state)
    assert len(calls) == 2


def test_unaccepted_changed_results_never_replace_existing_proof(unit_cache, monkeypatch):
    root, state, _ = unit_cache
    original = (state / "power-validation/project" / PLAN).read_bytes()
    (root / PLAN).write_bytes(original + b" ")

    def reject(_root):
        raise EvidenceError("original requirements no longer hold")

    monkeypatch.setattr(validation, "validate_simulation", reject)
    with pytest.raises(EvidenceError, match="requirements"):
        validation.validate_current(root, state_root=state)
    assert (state / "power-validation/project" / PLAN).read_bytes() == original


def test_replacing_retained_output_with_a_hardlink_invalidates_acceptance(unit_cache):
    root, state, _ = unit_cache
    retained = root / "power/results/retained/nominal_coarse/wave.raw"
    retained.unlink()
    retained.hardlink_to(root / "power/results/native/nominal_coarse/wave.raw")
    with pytest.raises(EvidenceError, match="independent copy"):
        validation.validate_current(root, state_root=state)


def test_project_copy_cannot_replace_runtime_state(unit_cache):
    root, state, _ = unit_cache
    accepted = state / "power-validation"
    copied = root / "manufactured-validation"
    accepted.rename(copied)
    accepted.symlink_to(copied, target_is_directory=True)
    with pytest.raises(EvidenceError, match="symbolic link"):
        validation.validate_current(root, state_root=state)


def test_changes_during_validation_are_not_persisted(work, tmp_path, monkeypatch):
    state = tmp_path / "state"

    def change(_root):
        path = work / PLAN
        path.write_bytes(path.read_bytes() + b" ")

    monkeypatch.setattr(validation, "validate_simulation", change)
    with pytest.raises(EvidenceError, match="changed during"):
        validation.validate_current(work, state_root=state)
    assert not (state / "power-validation").exists()


def test_tool_or_implementation_change_requires_revalidation(unit_cache, tmp_path, monkeypatch):
    root, state, calls = unit_cache
    monkeypatch.setattr(native, "version", lambda: "changed-native-version")
    validation.validate_current(root, state_root=state)
    assert len(calls) == 2
    code = tmp_path / "changed-implementation.py"
    code.write_text("implementation revision")
    sources = validation._sources
    monkeypatch.setattr(validation, "_sources", lambda root: {**sources(root), "implementation/change.py": code})
    validation.validate_current(root, state_root=state)
    assert len(calls) == 3
    code.write_text("new implementation revision")
    validation.validate_current(root, state_root=state)
    assert len(calls) == 4


def test_running_checker_cannot_certify_source_different_from_its_loaded_code(unit_cache, monkeypatch):
    root, state, _ = unit_cache
    loaded = dict(validation._LOADED_IMPLEMENTATION)
    loaded["implementation/power/validation.py"] += b"previous loaded revision"
    monkeypatch.setattr(validation, "_LOADED_IMPLEMENTATION", loaded)
    with pytest.raises(EvidenceError, match="restart"):
        validation.validate_current(root, state_root=state)


def test_missing_or_corrupt_host_record_is_not_accepted(unit_cache):
    root, state, _ = unit_cache
    path = state / "power-validation/VALIDATED.json"
    path.write_text("invalid JSON")
    with pytest.raises(EvidenceError, match="cannot read JSON"):
        validation.validate_current(root, state_root=state)
    path.unlink()
    with pytest.raises(EvidenceError):
        validation.validate_current(root, state_root=state)


def test_project_local_proof_is_not_trusted(work, monkeypatch):
    calls = []
    monkeypatch.setattr(validation, "validate_simulation", lambda root: calls.append(root))
    validation.validate_current(work, state_root=work / ".local-state")
    validation.validate_current(work, state_root=work / ".local-state")
    assert len(calls) == 2
    assert not (work / ".local-state").exists()


def test_without_runtime_state_the_public_checker_always_replays(work, monkeypatch):
    monkeypatch.delenv("ARGUS_SKILL_SESSION_ROOT", raising=False)
    calls = []
    monkeypatch.setattr(validation, "validate_simulation", lambda root: calls.append(root))
    validation.validate_current(work)
    validation.validate_current(work)
    assert len(calls) == 2
