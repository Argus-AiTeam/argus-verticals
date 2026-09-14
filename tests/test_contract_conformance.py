"""The community gate: every vertical here is a valid Argus plugin.

Argus discovers out-of-tree verticals through the ``argus_skill.verticals``
entry-point group (``argus_skill/verticals/_registry.py``) and validates each
one with ``argus_skill.core.vertical_contract.vertical_contract``. This module
runs those same checks against ``pyproject.toml`` directly, so a contributor
learns before a release that a vertical would be silently dropped from the
Manager's menu. It also pins the repository's own rules: one directory per
vertical, each registered exactly once, each with a README.

The contract is exercised directly rather than through
``argus_skill.verticals._base.load_vertical`` because that loader prefers an
in-tree copy of the same name when one exists.
"""
from __future__ import annotations

import importlib
import re
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import pytest
from argus_skill.core.vertical_contract import vertical_contract
from argus_skill.skills.vertical_select import VERTICALS as ARGUS_BUILTIN_VERTICALS
from argus_skill.verticals._registry import ENTRY_POINT_GROUP, VERTICAL_API_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "argus_verticals"
# Mirrors the registry's accepted name shape.
ENTRY_POINT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
SKILL_ROLE_DIRS = frozenset({"manager", "planner", "engineer", "reviewer", "references"})


def _entry_points() -> dict[str, str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(data["project"]["entry-points"][ENTRY_POINT_GROUP])


def _vertical_stage_modules() -> set[str]:
    """Dotted module path of every ``stages.py`` under the package."""
    return {
        ".".join(("argus_verticals", *path.relative_to(PACKAGE_ROOT).parent.parts, "stages"))
        for path in PACKAGE_ROOT.rglob("stages.py")
    }


def _module_dir(target: str) -> Path:
    return PACKAGE_ROOT.joinpath(*target.split(".")[1:-1])


ENTRY_POINTS = _entry_points()


@pytest.mark.parametrize(("name", "target"), sorted(ENTRY_POINTS.items()))
def test_plugin_module_satisfies_the_argus_contract(name: str, target: str) -> None:
    module = importlib.import_module(target)

    assert module.ARGUS_VERTICAL_API_VERSION == VERTICAL_API_VERSION, (
        f"{name}: ARGUS_VERTICAL_API_VERSION must equal Argus's VERTICAL_API_VERSION"
    )
    purpose = module.VERTICAL_PURPOSE
    assert isinstance(purpose, str) and purpose.strip(), f"{name}: VERTICAL_PURPOSE is empty"

    skills = getattr(module, "VERTICAL_SKILLS", None)
    if skills is not None:
        skills = Path(skills)
        assert skills.is_dir(), f"{name}: VERTICAL_SKILLS {skills} is not a directory"
        assert skills == _module_dir(target) / "skills", (
            f"{name}: VERTICAL_SKILLS must be the vertical's own skills/ directory"
        )
        assert any(skills.rglob("*.md")), f"{name}: skills/ holds no markdown"
        stray = sorted(p.name for p in skills.iterdir() if p.is_dir() and p.name not in SKILL_ROLE_DIRS)
        assert not stray, f"{name}: skills/ subdirectories must be roles {sorted(SKILL_ROLE_DIRS)}: {stray}"
    else:
        assert not (_module_dir(target) / "skills").is_dir(), (
            f"{name}: has a skills/ directory but does not declare VERTICAL_SKILLS"
        )

    parents = module.VERTICAL_SKILL_PARENTS
    assert isinstance(parents, tuple) and all(isinstance(p, str) for p in parents), (
        f"{name}: VERTICAL_SKILL_PARENTS must be a tuple of vertical names"
    )
    known = set(ENTRY_POINTS) | set(ARGUS_BUILTIN_VERTICALS)
    assert set(parents) <= known, f"{name}: unknown skill parents {sorted(set(parents) - known)}"
    assert name not in parents, f"{name}: a vertical cannot be its own skill parent"

    # The same validation Argus's registry runs; raises VerticalContractError.
    contract = vertical_contract(name, module)
    assert contract.stage_order


@pytest.mark.parametrize(("name", "target"), sorted(ENTRY_POINTS.items()))
def test_every_vertical_has_a_readme(name: str, target: str) -> None:
    readme = _module_dir(target) / "README.md"
    assert readme.is_file(), f"{name}: add {readme.relative_to(REPO_ROOT)}"
    assert readme.read_text(encoding="utf-8").strip(), f"{name}: README.md is empty"


def test_entry_point_names_are_valid_and_match_their_directories() -> None:
    for name, target in ENTRY_POINTS.items():
        assert ENTRY_POINT_NAME.fullmatch(name), f"invalid entry-point name {name!r}"
        parts = target.split(".")
        assert parts[0] == "argus_verticals" and parts[-1] == "stages", (
            f"{name}: entry point must target argus_verticals.<vertical>.stages, got {target}"
        )
        assert name == "_".join(parts[1:-1]), (
            f"{name}: entry-point name must be the vertical's directory path joined with '_'"
        )
    assert len(set(ENTRY_POINTS.values())) == len(ENTRY_POINTS), "a module is registered twice"


def test_every_vertical_directory_is_registered_exactly_once() -> None:
    registered = set(ENTRY_POINTS.values())
    present = _vertical_stage_modules()
    assert registered == present, (
        "pyproject.toml [project.entry-points.\"argus_skill.verticals\"] and the "
        "argus_verticals/ tree disagree.\n"
        f"  registered but missing on disk: {sorted(registered - present)}\n"
        f"  on disk but not registered:     {sorted(present - registered)}"
    )


def test_purposes_are_distinct() -> None:
    """The Manager picks a vertical from these one-liners; duplicates are unroutable."""
    purposes = {name: importlib.import_module(t).VERTICAL_PURPOSE.strip() for name, t in ENTRY_POINTS.items()}
    seen: dict[str, str] = {}
    for name, purpose in purposes.items():
        assert purpose not in seen, f"{name} and {seen[purpose]} share a VERTICAL_PURPOSE"
        seen[purpose] = name


def test_argus_discovers_the_installed_plugins() -> None:
    """End-to-end through Argus's registry; needs this package installed."""
    try:
        distribution("argus-verticals")
    except PackageNotFoundError:
        pytest.skip("argus-verticals is not installed; run `pip install -e .` to test discovery")
    from argus_skill.verticals._registry import vertical_plugins

    plugins = vertical_plugins()
    missing = sorted(set(ENTRY_POINTS) - set(plugins))
    assert not missing, f"Argus's registry did not accept: {missing} (see its log for the reason)"
    for name, target in ENTRY_POINTS.items():
        module = importlib.import_module(target)
        plugin = plugins[name]
        assert plugin.module is module
        assert plugin.purpose == module.VERTICAL_PURPOSE.strip()
        declared = getattr(module, "VERTICAL_SKILLS", None)
        assert (plugin.skills_root is None) == (declared is None)
        if declared is not None:
            assert Path(plugin.skills_root) == Path(declared)
