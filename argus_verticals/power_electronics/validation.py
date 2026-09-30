"""Reuse native agreement only while every numerical input and result is unchanged."""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from argus.core.file_lock import exclusive_file_lock

from argus_verticals.hardware.shared import evidence as shared_evidence
from argus_verticals.hardware.shared.evidence import EvidenceError, project_file, record
from argus_verticals.hardware.spice import raw

from . import native
from .evidence import validate_simulation
from .model import PLAN, RESULTS
from .robustness import ASSESSMENT, MAX_STUDY_SECONDS

log = logging.getLogger(__name__)


def _implementation_sources() -> dict[str, Path]:
    return {
        **{f"implementation/power/{p.name}": p for p in Path(__file__).parent.glob("*.py")},
        "implementation/shared/evidence.py": Path(shared_evidence.__file__),
        "implementation/spice/raw.py": Path(raw.__file__),
    }


_LOADED_IMPLEMENTATION = {key: path.read_bytes() for key, path in _implementation_sources().items()}


def _sources(root: Path) -> dict[str, Path]:
    result = record(root, RESULTS)
    paths = {PLAN, RESULTS}
    if "robustness" in record(root, PLAN):
        paths.add(ASSESSMENT)
    for field in ("inputs", "outputs"):
        mapping = result.get(field)
        if not isinstance(mapping, dict) or any(not isinstance(v, str) for v in mapping.values()):
            raise EvidenceError(f"{field}: expected original file and independent-copy paths")
        for source, copy in mapping.items():
            if project_file(root, source).samefile(project_file(root, copy)):
                raise EvidenceError(f"{field}: missing independent copy of {source}")
        paths.update(mapping)
        paths.update(mapping.values())
    sources = {f"project/{p}": project_file(root, p) for p in paths}
    implementation = _implementation_sources()
    if {key: path.read_bytes() for key, path in implementation.items()} != _LOADED_IMPLEMENTATION:
        raise EvidenceError("checker implementation changed in a running process; restart it before validation")
    sources.update(implementation)
    binary = shutil.which("ngspice")
    if binary is None:
        raise EvidenceError("native ngspice is required")
    sources["implementation/ngspice"] = Path(binary).resolve()
    return sources


def _unchanged(copies: Path, sources: dict[str, Path]) -> bool:
    for relative, source in sources.items():
        saved = copies / relative
        if not saved.is_file() or saved.is_symlink() or not saved.resolve().is_relative_to(copies):
            return False
        if saved.samefile(source) or saved.read_bytes() != source.read_bytes():
            return False
    return True


def validate_current(root: Path, *, state_root: Path | None = None) -> None:
    """Keep reusable proof in runtime state, never in agent-produced result records."""
    root = root.resolve()
    configured = state_root or os.environ.get("ARGUS_SKILL_SESSION_ROOT")
    if configured is None:
        validate_simulation(root)
        return
    state = Path(configured).resolve()
    if state.is_relative_to(root):
        validate_simulation(root)
        return
    try:
        state.mkdir(parents=True, exist_ok=True)
        with (state / "power-validation.lock").open("a+b") as lock, exclusive_file_lock(
            lock, timeout_seconds=MAX_STUDY_SECONDS, lock_name="power numerical validation",
        ):
            sources = _sources(root)
            identity = {
                "project_root": str(root), "ngspice_version": native.version(),
                "numpy_version": np.__version__, "python_version": sys.version,
                "files": sorted(sources),
            }
            accepted = state / "power-validation"
            if accepted.is_symlink():
                raise EvidenceError("validated numerical state must not be a symbolic link")
            if accepted.exists():
                saved = record(accepted, "VALIDATED.json")
                if saved == identity and _unchanged(accepted, sources):
                    return
                log.info("Power numerical inputs or results changed; running native replay.")
            with tempfile.TemporaryDirectory(prefix=".power-validation-", dir=state) as directory:
                pending = Path(directory)
                for relative, source in sources.items():
                    target = pending / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                validate_simulation(root)
                if not _unchanged(pending, sources) or _sources(root) != sources:
                    raise EvidenceError("numerical files changed during independent validation")
                (pending / "VALIDATED.json").write_text(json.dumps(identity, indent=2) + "\n")
                if accepted.exists():
                    shutil.rmtree(accepted)
                pending.rename(accepted)
    except (OSError, TimeoutError) as exc:
        raise EvidenceError(f"cannot retain or compare validated numerical files: {exc}") from exc
