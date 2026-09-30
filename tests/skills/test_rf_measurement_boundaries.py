from __future__ import annotations

import json

import numpy as np
import pytest
import skrf as rf

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.rf_design.evidence import RESULTS
from argus_verticals.rf_design.networks import measurement, read_touchstone
from argus_verticals.rf_design.robustness import headroom, inspect_study
from argus_verticals.rf_design.run_analysis import run_analysis
from argus_verticals.rf_design.run_robustness_reference import prepare_reference
from argus_verticals.rf_design.study import resolve_study


def test_db_check_does_not_require_unselected_zero_frequency():
    network = rf.Network(f=[1e9, 2e9, 3e9], s=np.array([0, 0.5, 0.25]).reshape(-1, 1, 1), z0=50)
    check = {"metric": "s_db", "ports": [1, 1], "statistic": "max", "window_hz": [2e9, 3e9]}
    assert measurement(network, check) == (20*np.log10(0.5), "dB", 2e9)


@pytest.mark.parametrize("at", [2e9, 2.5e9])
def test_db_point_uses_only_its_interpolation_support(at):
    network = rf.Network(f=[1e9, 2e9, 3e9], s=np.array([0, 0.5, 0.25]).reshape(-1, 1, 1), z0=50)
    check = {"metric": "s_db", "ports": [1, 1], "statistic": "at", "at_hz": at}
    value, unit, frequency = measurement(network, check)
    expected = np.interp(at, [2e9, 3e9], 20*np.log10([0.5, 0.25]))
    assert value == expected and unit == "dB" and frequency == at


@pytest.mark.parametrize("window", [[1e9, 3e9], [1.5e9, 3e9]])
def test_db_check_still_rejects_zero_in_selected_or_bracketing_samples(window):
    network = rf.Network(f=[1e9, 2e9, 3e9], s=np.array([0, 0.5, 0.25]).reshape(-1, 1, 1), z0=50)
    with pytest.raises(EvidenceError, match="zero S parameter"):
        measurement(network, {"metric": "s_db", "ports": [1, 1], "statistic": "max", "window_hz": window})


def test_exact_decimal_margin_does_not_falsely_fail_an_ideal_resistor(tmp_path):
    root = tmp_path / "margin"
    prepare_reference(root)
    path = root / "design/rf-study.json"
    spec = json.loads(path.read_text())
    spec["networks"]["match"]["z0_ohm"] = [50, 50]
    spec["networks"]["match"]["elements"] = [{"kind": "R", "connection": "series", "value_si": 100}]
    spec["parameters"] = {
        "r": {"network": "match", "element": 1, "nominal": 100, "minimum": 50, "maximum": 100,
              "unit": "ohm", "source": "Original ideal resistor reference."},
    }
    spec["axes"] = [{"id": "r_sample", "parameter": "r", "unit": "1", "factors": [0.5, 1],
                     "source": "Explicit ideal resistor samples."}]
    spec["studies"][0]["checks"] = [
        {"id": "reflection", "requirement": "band", "metric": "s_magnitude", "ports": [1, 1],
         "statistic": "max", "window_hz": [0.8e9, 1.2e9], "unit": "1",
         "minimum": 0, "maximum": 0.7, "margin_upper": 0.2, "max_delta": 0},
    ]
    path.write_text(json.dumps(spec, indent=2) + "\n")
    report = run_analysis(root)
    assert report["task_accepted"] and report["status"] == "passed"
    worst = report["checks"][0]["worst_observed_upper"]
    assert worst["value"] == 0.5
    assert worst["upper_headroom"] == 0.2 and worst["upper_margin_surplus"] == 0


@pytest.mark.parametrize("value,passed", [
    (0.5, True),
    (np.nextafter(0.5, 0.0), True),
    (np.nextafter(0.5, 1.0), False),
])
def test_exact_upper_margin_does_not_admit_one_step_beyond(value, passed):
    observed = headroom(float(value), {"minimum": 0, "maximum": 0.7, "margin_upper": 0.2})
    assert observed["required_margins_met"] is passed
    assert observed["within_limits"]


@pytest.mark.parametrize("value,passed", [
    (0.3, True),
    (np.nextafter(0.3, 1.0), True),
    (np.nextafter(0.3, 0.0), False),
])
def test_exact_lower_margin_does_not_admit_one_step_beyond(value, passed):
    observed = headroom(float(value), {"minimum": 0.1, "maximum": 1, "margin_lower": 0.2})
    assert observed["required_margins_met"] is passed
    assert observed["within_limits"]


def test_original_bounds_remain_strict_with_no_margins():
    assert not headroom(float(np.nextafter(0.7, 1.0)), {"minimum": 0, "maximum": 0.7})["within_limits"]
    assert not headroom(float(np.nextafter(0.1, 0.0)), {"minimum": 0.1, "maximum": 1})["within_limits"]


def test_overflowed_headroom_is_an_explicit_failure():
    with pytest.raises(EvidenceError, match="overflowed"):
        headroom(1e308, {"minimum": -1e308, "maximum": 1e308})


def test_phase_retains_its_original_global_unwrap_branch():
    phases = np.array([170, 190, 210])
    network = rf.Network(f=[1e9, 2e9, 3e9], s=np.exp(1j*np.deg2rad(phases)).reshape(-1, 1, 1), z0=50)
    value, unit, frequency = measurement(network, {
        "metric": "s_phase_deg", "ports": [1, 1], "statistic": "max", "window_hz": [2e9, 3e9],
    })
    assert value == pytest.approx(210) and unit == "deg" and frequency == 3e9


@pytest.mark.parametrize("upper,valid", [(0.2, True), (float(np.nextafter(0.2, 1.0)), False)])
def test_decimal_margin_fit_does_not_relax_original_window(tmp_path, upper, valid):
    root = tmp_path / "fit"
    prepare_reference(root)
    path = root / "design/rf-study.json"
    spec = json.loads(path.read_text())
    spec["studies"][0]["checks"][0].update(minimum=0, maximum=0.3, margin_lower=0.1, margin_upper=upper)
    path.write_text(json.dumps(spec) + "\n")
    if valid:
        assert resolve_study(root)
    else:
        with pytest.raises(EvidenceError, match="do not fit"):
            resolve_study(root)


def test_real_lc_null_outside_checked_band_does_not_invalidate_robustness(tmp_path):
    root = tmp_path / "lc"
    prepare_reference(root)
    path = root / "design/rf-study.json"
    spec = json.loads(path.read_text())
    value = 1/(2*np.pi*1e9)
    spec["networks"]["match"].update(z0_ohm=[50, 50], elements=[
        {"kind": "L", "connection": "series", "value_si": value},
        {"kind": "C", "connection": "series", "value_si": value},
    ])
    spec["parameters"] = {
        "l": {"network": "match", "element": 1, "nominal": value, "minimum": value/2, "maximum": value*2,
              "unit": "H", "source": "Original ideal series LC reference."},
    }
    spec["axes"] = [{"id": "l_tolerance", "parameter": "l", "unit": "1", "factors": [0.95, 1.05],
                     "source": "Explicit component samples."}]
    spec["studies"][0]["checks"] = [
        {"id": "reflection_db", "requirement": "band", "metric": "s_db", "ports": [1, 1],
         "statistic": "max", "window_hz": [1.1e9, 1.2e9], "unit": "dB",
         "minimum": -100, "maximum": 0, "max_delta": 1e-10},
    ]
    path.write_text(json.dumps(spec, indent=2) + "\n")
    report = run_analysis(root)
    assert report["task_accepted"]
    result = json.loads((root / RESULTS).read_text())
    native = read_touchstone(root, result["cases"][0]["studies"][0]["path"])
    assert native.s[native.f.tolist().index(1e9), 0, 0] == 0
    assert inspect_study(root) == report
