"""Skill-seeding contract for the nanochat vertical (from Argus's ``tests/skills/test_builtins_seeding.py``).

nanochat ships no ``skills/`` of its own and deliberately does not inherit the
H100-specific speedrun traces: its fixed-budget quality objective follows the
project's frozen harness. Argus keeps the digests of the retired machine-specific
playbooks so an old seeded copy is recognised and replaced.
"""
from __future__ import annotations

from argus_skill.skills.builtins import (
    _RETIRED_BUILTIN_SEED_HASHES,
    iter_vertical_skill_texts,
)
from argus_skill.verticals._base import load_vertical
from argus_skill.verticals._registry import vertical_plugin

RETIRED_NANOCHAT_SKILLS = {
    "engineer/nanochat-autoresearch-hands-on-trace.md",
    "engineer/nanochat-autoresearch-sota-optimization.md",
    "engineer/nanochat-pretrain-runner.md",
}


def test_nanochat_is_registered_without_skills_or_parents() -> None:
    plugin = vertical_plugin("nanochat")
    assert plugin is not None, "nanochat is not registered with Argus's plugin registry"
    assert plugin.module.__name__ == "argus_verticals.nanochat.stages"
    assert load_vertical("nanochat") is plugin.module
    assert plugin.skills_root is None
    assert plugin.skill_parents == ()


def test_machine_specific_nanochat_playbooks_are_retired() -> None:
    packaged = {name for name, _text in iter_vertical_skill_texts("nanochat")}

    assert packaged == set()
    assert RETIRED_NANOCHAT_SKILLS <= _RETIRED_BUILTIN_SEED_HASHES.keys()
