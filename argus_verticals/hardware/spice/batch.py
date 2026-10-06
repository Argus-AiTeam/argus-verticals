"""Run native SPICE with isolated startup settings and bounded retained output."""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.hardware.shared.native import run_monitored


def version() -> str:
    try:
        result = subprocess.run(["ngspice", "-n", "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"native ngspice is required: {exc}") from exc
    match = re.search(r"\bngspice-(\d+(?:\.\d+)?)\b", result.stdout + result.stderr)
    if result.returncode != 0 or match is None or int(match[1].split(".")[0]) < 42:
        raise EvidenceError("this adapter requires native ngspice >=42")
    return match[1]


def run_batch(command: list[str], cwd: Path, output: Path, files: tuple[str, ...], *,
              timeout: float, output_budget: int, save=None) -> dict:
    home = output / "config"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPICE", "NGSPICE"))}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home), SPICE_ASCIIRAWFILE="1", LC_ALL="C", OMP_NUM_THREADS="1")
    row = {"command": command, "cwd": str(cwd), "log": str(output / "ngspice.log"), "exit_code": None}
    if save:
        save(row)
    def limit(deadline: float) -> str:
        if time.monotonic() >= deadline:
            return f"native simulation exceeded {timeout:g} seconds"
        if sum((output / name).stat().st_size for name in files if (output / name).exists()) > output_budget:
            return f"native output exceeded {output_budget} bytes"
        return ""

    try:
        with (output / "console.log").open("w") as console:
            row["exit_code"], stopped = run_monitored(
                command, root=cwd, stream=console, env=env,
                deadline=time.monotonic() + timeout, limit=limit,
            )
    except OSError as exc:
        raise EvidenceError(f"ngspice execution failed: {exc}") from exc
    if save:
        save(row)
    if stopped or row["exit_code"] != 0:
        raise EvidenceError(f"{stopped or 'ngspice failed'}; inspect {output}")
    return row
