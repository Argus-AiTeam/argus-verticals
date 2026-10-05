"""Reuse native agreement only while every numerical input and result is unchanged."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from argus_verticals.hardware.shared import evidence as shared_evidence
from argus_verticals.hardware.shared import native as shared_native
from argus_verticals.hardware.shared.evidence import record
from argus_verticals.hardware.spice import batch, raw
from argus_verticals.hardware.spice import validation as cached

from . import native
from .evidence import validate_simulation
from .model import PLAN, RESULTS
from .robustness import ASSESSMENT


def _implementation_sources() -> dict[str, Path]:
    return {
        **{f"implementation/power/{p.name}": p for p in Path(__file__).parent.glob("*.py")},
        "implementation/shared/evidence.py": Path(shared_evidence.__file__),
        "implementation/shared/native.py": Path(shared_native.__file__),
        "implementation/spice/raw.py": Path(raw.__file__),
        "implementation/spice/batch.py": Path(batch.__file__),
        "implementation/spice/validation.py": Path(cached.__file__),
    }


_LOADED_IMPLEMENTATION = {key: path.read_bytes() for key, path in _implementation_sources().items()}


def _sources(root: Path) -> dict[str, Path]:
    paths = {PLAN, RESULTS}
    if "robustness" in record(root, PLAN):
        paths.add(ASSESSMENT)
    return cached.bound_sources(root, RESULTS, paths, _implementation_sources(), _LOADED_IMPLEMENTATION)


def validate_current(root: Path, *, state_root: Path | None = None) -> None:
    """Keep reusable proof in runtime state, never in agent-produced result records."""
    root = root.resolve()
    cached.validate_cached(
        root, "power-validation", state_root=state_root, sources=lambda: _sources(root),
        versions=lambda: {"ngspice_version": native.version(), "numpy_version": np.__version__},
        validate=lambda: validate_simulation(root),
    )
