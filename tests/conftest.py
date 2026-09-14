"""Test-suite isolation for the community verticals.

These fixtures re-create the isolation the moved tests silently relied on in
Argus's own ``tests/conftest.py``: every test gets throwaway Argus state roots
and its own working directory, and a test that writes project state into the
checkout fails. Some tests drive real Argus entry points (``Manager``,
``resolve_vertical``, the stage machine); without the state-root pin they would
write into the developer's real ``~/.argus-skill``.

Nothing here imports from Argus's ``tests`` package; this file is
self-contained so the suite runs against an installed ``argus-skill``.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def require_symlink_support(tmp_path: Path) -> None:
    """Skip only when this host cannot create the symlinks a test requires.

    Windows supports symlinks when Developer Mode or the corresponding account
    privilege is enabled. Treat that as a runtime capability instead of
    skipping every Windows host.
    """
    probe = tmp_path / "symlink-capability"
    probe.mkdir()
    file_target = probe / "file-target"
    file_target.write_text("probe\n", encoding="utf-8")
    directory_target = probe / "directory-target"
    directory_target.mkdir()
    try:
        (probe / "file-link").symlink_to(file_target)
        (probe / "directory-link").symlink_to(
            directory_target,
            target_is_directory=True,
        )
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"host cannot create test symlinks: {exc}")


@pytest.fixture(autouse=True)
def _isolate_argus_state_roots(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point every Argus state root at a throwaway directory for this test.

    Ambient ``ARGUS_SKILL_*`` variables steer backend, model, and budget
    resolution, so a developer shell that exports one silently changes what
    the suite exercises. ``COPILOT_HOME`` is just as stateful. Start from a
    clean slate; a test that needs a value sets it itself
    (``monkeypatch.setenv`` inside the test body runs after this fixture).

    ``ARGUS_SKILL_SOURCE_ROOT`` deliberately stays unset: setting it arms
    Argus's source-root startup preflight.
    """
    root = Path(tmp_path_factory.mktemp("argus-home"))
    for name in [k for k in os.environ if k.startswith("ARGUS_SKILL_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    monkeypatch.setenv("ARGUS_SKILL_HOME", str(root))
    # Model resolution inspects Codex's provider config; never let a
    # developer's ~/.codex/config.toml change default-model assertions.
    monkeypatch.setenv("CODEX_HOME", str(root / "codex-home"))


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Keep collection-time imports in safe mode.

    The per-test fixture above re-points every state root, but module import
    happens before it runs; safe mode keeps any import-time side effect from
    reaching a real sandbox escape.
    """
    os.environ.setdefault("ARGUS_SKILL_SAFE_MODE", "1")


@pytest.fixture(autouse=True)
def _isolate_working_directory(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Give every test its own working directory instead of the checkout.

    Much of the Argus runtime resolves "which project am I?" from the process
    cwd (``resolve_project_root``, ``resolve_vertical``,
    ``PIPELINE_STATE.json`` lookups). Under pytest that cwd would be this
    checkout, so a test would silently adopt the repository as its project. A
    test that needs a specific directory calls ``monkeypatch.chdir`` itself.
    """
    workdir = tmp_path_factory.mktemp("workdir")
    monkeypatch.chdir(workdir)
    return workdir


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _forbid_project_state_in_the_checkout() -> Iterator[None]:
    """Fail a test that writes project state into this source tree.

    The cwd fixture removes the usual way this happens, but a test can still
    pass an explicit path. The files the runtime creates to mark a project are
    named, so their appearance in the checkout is unambiguous.
    """
    root = _repo_root()
    markers = (".argus/PIPELINE_STATE.json", "research/CHECKLISTS.json", ".autors")
    before = {name for name in markers if (root / name).exists()}
    yield
    leaked = sorted(
        name for name in markers if (root / name).exists() and name not in before
    )
    assert not leaked, (
        f"test wrote project state into the source checkout: {leaked}. "
        "Give the Manager/supervisor an explicit workdir under tmp_path."
    )


@pytest.fixture(autouse=True)
def _no_stop_leaks_between_tests():
    """Argus's process-wide stop flag outlives a test by design; clear it on
    both sides so one test's stop request cannot change what an unrelated
    test observes."""
    from argus_skill.core import process_stop

    process_stop.clear_stop()
    yield
    process_stop.clear_stop()
