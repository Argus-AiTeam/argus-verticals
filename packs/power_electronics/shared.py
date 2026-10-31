"""File/number checks, the bounded ngspice runner and the ASCII transient reader.

Adapted from the Argus hardware/shared (evidence.py, native.py) and hardware/spice (batch.py, raw.py),
keeping only what the converter studies use. Standard library only.
"""
from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

MAX_RAW_BYTES = 64 * 1024 * 1024
UNITS = {"voltage": "V", "current": "A", "time": "s"}


class EvidenceError(ValueError):
    pass


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


def run_monitored(command: list[str], *, root: Path, stream, deadline: float, limit, env=None) -> tuple[int, str]:
    """Run one owned native command, stopping it (and its process group) when `limit` reports a reason."""
    stopped = ""
    with subprocess.Popen(
        command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            while process.poll() is None:
                if stopped := limit(deadline):
                    break
                time.sleep(0.05)
        finally:
            finished = process.poll() is not None
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    if finished and not stopped:
                        stopped = "native command left owned child processes running"
                except ProcessLookupError:
                    pass
            elif not finished:
                process.kill()
            exit_code = process.wait()
    return exit_code, stopped or limit(deadline)


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
    """Run native SPICE with isolated startup settings and bounded retained output."""
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


@dataclass(frozen=True)
class Plot:
    variables: tuple[tuple[str, str], ...]
    rows: tuple[tuple[complex, ...], ...]

    def signal(self, name: str) -> tuple[list[complex], str]:
        for index, (vector, quantity) in enumerate(self.variables):
            if vector == name.lower():
                if index == 0:
                    raise EvidenceError("measure a signal, not the independent sweep axis")
                if quantity not in UNITS:
                    raise EvidenceError(f"unsupported signal quantity: {quantity}")
                return [row[index] for row in self.rows], UNITS[quantity]
        raise EvidenceError(f"native output does not contain vector {name!r}; check .save")


def read_plot(path: Path) -> Plot:
    """Read one ASCII ngspice transient plot."""
    try:
        if path.stat().st_size > MAX_RAW_BYTES:
            raise ValueError("native waveform exceeds the 64 MiB reader limit")
        lines = iter(path.read_text(encoding="ascii").splitlines())
        header = {}
        for line in lines:
            if line.strip() == "Variables:":
                break
            key, value = line.split(":", 1)
            if key in header:
                raise ValueError(f"duplicate header {key}")
            header[key] = value.strip()
        if header.get("Plotname") != "Transient Analysis":
            raise ValueError("native plot does not match the requested analysis")
        if header.get("Flags") != "real":
            raise ValueError("expected real native values")
        nvars, npoints = int(header["No. Variables"]), int(header["No. Points"])
        if not 1 <= nvars <= 128 or not 1 <= npoints <= 100_000:
            raise ValueError("expected 1-128 vectors and 1-100000 points")
        variables = []
        for index in range(nvars):
            fields = next(lines).split()
            if len(fields) < 3 or fields[0] != str(index):
                raise ValueError("invalid native variable index")
            variables.append((fields[1].lower(), fields[2].lower()))
        if len({name for name, _ in variables}) != nvars:
            raise ValueError("duplicate native vectors")
        if next(lines).strip() != "Values:":
            raise ValueError("expected ASCII Values; use the supplied batch runner")
        rows = []
        for point in range(npoints):
            row = []
            for index in range(nvars):
                value = next(lines).strip()
                if index == 0:
                    ordinal, value = value.split(None, 1)
                    if ordinal != str(point):
                        raise ValueError("invalid native point index")
                pieces = value.split(",")
                if len(pieces) != 1:
                    raise ValueError("wrong number of real/imaginary components")
                parsed = complex(float(pieces[0]), 0)
                if not math.isfinite(parsed.real):
                    raise ValueError("nonfinite native signal")
                row.append(parsed)
            rows.append(tuple(row))
        if any(line.strip() for line in lines):
            raise ValueError("extra data or multiple plots; use one analysis per deck")
        if variables[0][1] != "time" or npoints < 2:
            raise ValueError("invalid independent axis or insufficient points")
        axis = [row[0].real for row in rows]
        if min(axis) < 0:
            raise ValueError("negative time")
        if any(a >= b for a, b in zip(axis, axis[1:])):
            raise ValueError("expected a strictly increasing one-dimensional axis")
        return Plot(tuple(variables), tuple(rows))
    except (OSError, UnicodeError, ValueError, KeyError, StopIteration) as exc:
        raise EvidenceError(f"{path.name}: invalid native ngspice output: {exc}") from exc
