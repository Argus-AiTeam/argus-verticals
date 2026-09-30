"""Retain accepted native agreement outside the execution project."""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from argus.core.file_lock import exclusive_file_lock

from argus_verticals.hardware.shared.evidence import EvidenceError, project_file, record

log = logging.getLogger(__name__)


def bound_sources(root: Path, result_path: str, records: set[str], implementation: dict[str, Path],
                  loaded_implementation: dict[str, bytes]) -> dict[str, Path]:
    result = record(root, result_path)
    paths = set(records)
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
    if {key: path.read_bytes() for key, path in implementation.items()} != loaded_implementation:
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


def validate_cached(root: Path, name: str, *, state_root: Path | None,
                    sources: Callable[[], dict[str, Path]], versions: Callable[[], dict],
                    validate: Callable[[], object]) -> None:
    configured = state_root or os.environ.get("ARGUS_SKILL_SESSION_ROOT")
    if configured is None or Path(configured).resolve().is_relative_to(root):
        validate()
        return
    state = Path(configured).resolve()
    try:
        state.mkdir(parents=True, exist_ok=True)
        with (state / f"{name}.lock").open("a+b") as lock, exclusive_file_lock(
            lock, timeout_seconds=600, lock_name=name,
        ):
            current = sources()
            identity = {"project_root": str(root), "python_version": sys.version,
                        "files": sorted(current), **versions()}
            accepted = state / name
            if accepted.is_symlink():
                raise EvidenceError("validated numerical state must not be a symbolic link")
            if accepted.exists():
                saved = record(accepted, "VALIDATED.json")
                if saved == identity and _unchanged(accepted, current):
                    return
                log.info("Numerical inputs or results changed; running native replay.")
            with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=state) as directory:
                pending = Path(directory)
                for relative, source in current.items():
                    target = pending / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                validate()
                if not _unchanged(pending, current) or sources() != current:
                    raise EvidenceError("numerical files changed during independent validation")
                (pending / "VALIDATED.json").write_text(json.dumps(identity, indent=2) + "\n")
                if accepted.exists():
                    shutil.rmtree(accepted)
                pending.rename(accepted)
    except (OSError, TimeoutError) as exc:
        raise EvidenceError(f"cannot retain or compare validated numerical files: {exc}") from exc
