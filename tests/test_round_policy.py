"""Every vertical declares its own round guards.

Argus runs a mission with no fixed round ceiling; what remains are four
anti-livelock guards whose patience a vertical declares through
``ROUND_POLICY`` in its stages module (``argus/core/round_policy.py``). The
table below pins each vertical's choice so a change to one is deliberate:

- hardware and kernel correctness: Reviewer-judged stall streak of 8, round
  windows off, a missing progress judgement tolerated for 200 rounds;
- long metric-optimization loops: streak of 6, soft window off, 200;
- research-shaped work: streak of 6, soft window after 60, judgement from 120;
- bounded writing and editing: the framework defaults, written out.

An Argus from before per-vertical round policies never reads the attribute;
the contract still validates and the mission runs with that Argus's own
guards. That path is exercised whenever the installed Argus lacks
``argus.core.round_policy``.
"""
from __future__ import annotations

import importlib
import importlib.util
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "stall_threshold",
    "no_progress_threshold",
    "soft_round_limit",
    "hard_escalate_rounds",
)

VERIFY = (8, 2, 0, 200)
OPTIMIZE = (6, 2, 0, 200)
RESEARCH = (6, 2, 60, 120)
BOUNDED = (4, 2, 12, 24)

EXPECTED: dict[str, tuple[int, int, int, int]] = {
    "analog_mixed_signal": VERIFY,
    "chip_design": VERIFY,
    "digital_circuit": VERIFY,
    "digital_circuit_benchmark": VERIFY,
    "digital_circuit_verification": VERIFY,
    "fpga_design": VERIFY,
    "kernelbench": VERIFY,
    "package_design": VERIFY,
    "pcb_design": VERIFY,
    "power_electronics": VERIFY,
    "rf_design": VERIFY,
    "nanochat": OPTIMIZE,
    "nanogpt_speedrun": OPTIMIZE,
    "speedrun": OPTIMIZE,
    "ale_last_exam": RESEARCH,
    "materials": RESEARCH,
    "medical": RESEARCH,
    "physics": RESEARCH,
    "quant": RESEARCH,
    "classical_poetry": BOUNDED,
    "fiction_writing": BOUNDED,
    "literary_editor": BOUNDED,
    "modern_poetry": BOUNDED,
    "prose": BOUNDED,
}


def _entry_points() -> dict[str, str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(data["project"]["entry-points"]["argus.verticals"])


ENTRY_POINTS = _entry_points()


def _module(name: str):
    return importlib.import_module(ENTRY_POINTS[name])


def test_every_registered_vertical_has_a_policy_entry():
    assert set(EXPECTED) == set(ENTRY_POINTS)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_vertical_declares_its_round_policy(name):
    policy = getattr(_module(name), "ROUND_POLICY", None)
    assert isinstance(policy, dict), f"{name} declares no ROUND_POLICY mapping"
    assert tuple(policy) == FIELDS, f"{name} must declare all four guards, in order"
    for field, value in policy.items():
        assert type(value) is int and value >= 0, f"{name}.{field} = {value!r}"
    assert tuple(policy.values()) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_installed_argus_reads_or_ignores_the_policy(name):
    pytest.importorskip("argus")
    from argus.core.vertical_contract import vertical_contract

    module = _module(name)
    contract = vertical_contract(name, module)
    if importlib.util.find_spec("argus.core.round_policy") is None:
        # An Argus from before per-vertical round policies: the extra module
        # attribute is never read, and the contract still validates.
        assert not hasattr(contract, "round_policy")
        return
    from argus.core.round_policy import resolve_round_policy

    assert contract.round_policy is not None
    resolved = resolve_round_policy(contract.round_policy, env={}, persisted={})
    assert tuple(resolved.as_dict()[field] for field in FIELDS) == EXPECTED[name]
