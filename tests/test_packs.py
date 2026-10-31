"""The skill store's packs: the index Argus reads is the one scripts/build_packs.py makes, and every
pack stands alone once installed, outside this repository and without Python Argus."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_is_current() -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_packs.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_packs_import_nothing_from_argus() -> None:
    found = [str(path.relative_to(ROOT)) for path in (ROOT / "packs").rglob("*.py")
             if re.search(r"^\s*(from|import)\s+argus(_verticals)?\b", path.read_text(encoding="utf-8"), re.M)]
    assert not found, found
