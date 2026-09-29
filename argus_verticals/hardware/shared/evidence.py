"""Common file, numeric and command-record checks for hardware providers."""
from __future__ import annotations

import json
import math
import shlex
import sys
from pathlib import Path


class EvidenceError(ValueError):
    pass


def evidence_check_command(vertical: str, stage: str) -> str:
    script = (
        "from pathlib import Path; "
        "from argus.verticals._base import load_vertical_contract; "
        f"issues = load_vertical_contract({vertical!r}).completion_issues({stage!r}, Path.cwd()); "
        "print(list(issues)); raise SystemExit(bool(issues))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


def project_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise EvidenceError(f"expected a project-relative file, got {relative!r}")
    try:
        path = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"{relative}: {exc}") from exc
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size == 0:
        raise EvidenceError(f"{relative}: expected a nonempty file inside the project")
    return path


def record(root: Path, relative: str) -> dict:
    try:
        value = json.loads(project_file(root, relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{relative}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{relative}: expected a JSON object")
    return value


def names(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise EvidenceError(f"{field}: expected distinct nonempty strings")
    return value


def number(value: object, field: str, *, minimum: float = 0) -> float:
    message = f"{field}: expected a finite number >= {minimum}"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(message)
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise EvidenceError(message) from exc
    if not finite or value < minimum:
        raise EvidenceError(message)
    return value


def current_files(root: Path, payload: dict, required: list[str], *, field: str = "inputs") -> None:
    copies = payload.get(field)
    if not isinstance(copies, dict) or not set(required) <= copies.keys():
        raise EvidenceError(f"{field}: snapshots must include every required file")
    for source, snapshot in copies.items():
        source_path, copy_path = project_file(root, source), project_file(root, snapshot)
        if source_path.samefile(copy_path) or source_path.read_bytes() != copy_path.read_bytes():
            raise EvidenceError(f"{field}: missing independent copy or changed file {source}")


def command_result(root: Path, run: dict) -> str:
    command = run.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise EvidenceError("command: expected the actual argument vector")
    if type(run.get("exit_code")) is not int or run["exit_code"] != 0:
        raise EvidenceError("command did not exit successfully")
    try:
        return project_file(root, run.get("log")).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"cannot read command output: {exc}") from exc
