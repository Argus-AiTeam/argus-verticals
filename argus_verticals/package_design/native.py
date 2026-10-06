"""Execute Gmsh/CalculiX and interpret their real steady-state thermal fields."""
from __future__ import annotations

import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.hardware.shared.native import run_logged

from .mesh import Mesh, deck, geometry, read_mesh
from .model import temperature_offset

FILES = ("model.geo", "model.msh", "thermal.inp", "thermal.dat", "thermal.sta", "thermal.frd")


def versions() -> dict[str, str]:
    values = {}
    for name, command in (("gmsh", ["gmsh", "--version"]), ("calculix", ["ccx", "-v"])):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EvidenceError(f"native {name} is required: {exc}") from exc
        output = (result.stdout + result.stderr).strip()
        pattern = r"4\.\d+\.\d+" if name == "gmsh" else r"This is Version (2\.\d+)"
        match = re.fullmatch(pattern, output)
        allowed = (0,) if name == "gmsh" else (0, 201)
        if result.returncode not in allowed or match is None:
            raise EvidenceError(f"unsupported {name} version response: {output!r}")
        values[name] = match.group(0) if name == "gmsh" else match.group(1)
        if int(values[name].split(".")[1]) < (12 if name == "gmsh" else 21):
            raise EvidenceError("Gmsh >=4.12 within 4.x and CalculiX >=2.21 within 2.x are required")
    return values


def arguments(tool: str) -> list[str]:
    if tool == "gmsh":
        return ["gmsh", "model.geo", "-3", "-format", "msh2", "-nt", "1", "-v", "3", "-o", "model.msh"]
    if tool == "calculix":
        return ["ccx", "-i", "thermal"]
    raise EvidenceError("unknown native package tool")


def execute(model: dict, run: dict, output: Path, *, save=None) -> list[dict]:
    output.mkdir(parents=True, exist_ok=False)
    (output / "model.geo").write_text(geometry(model, run["mesh_size_m"]), encoding="utf-8")
    commands = []
    env = {key: value for key, value in os.environ.items() if not key.startswith(("GMSH", "CCX"))}
    home = output / "config"
    home.mkdir()
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home), OMP_NUM_THREADS="1", CCX_NPROC_RESULTS="1", NUMBER_OF_CPUS="1", LC_ALL="C")
    for tool in ("gmsh", "calculix"):
        if tool == "calculix":
            mesh = read_mesh(output / "model.msh", model)
            (output / "thermal.inp").write_text(deck(mesh, model, run), encoding="utf-8")
        log = output / f"{tool}.log"
        row = {"tool": tool, "command": arguments(tool), "cwd": str(output), "log": str(log), "exit_code": None}
        commands.append(row)
        if save is not None:
            save(commands)
        try:
            row["exit_code"], stopped = run_logged(
                arguments(tool), root=output, env=env, log=log, timeout=180,
            )
        except OSError as exc:
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"{tool}: {exc}\n")
            raise EvidenceError(f"{tool} execution failed: {exc}") from exc
        if stopped:
            row["stop_reason"] = stopped
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"{stopped}\n")
        if save is not None:
            save(commands)
        if stopped:
            raise EvidenceError(f"{tool}: {stopped}; inspect {log}")
        message = log.read_text(encoding="utf-8")
        if not message:
            log.write_text("(no console output)\n", encoding="utf-8")
        if row["exit_code"] != 0 or re.search(r"^\s*(?:Error\s*:|\*ERROR)", message, re.MULTILINE | re.IGNORECASE):
            raise EvidenceError(f"{tool} did not complete successfully; inspect {log}")
        if tool == "calculix" and "Job finished" not in message:
            raise EvidenceError("CalculiX did not report a finished job")
    return commands


def read_fields(path: Path, mesh: Mesh) -> tuple[dict[int, float], dict[int, float]]:
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise EvidenceError("CalculiX field data is missing or exceeds 32 MiB")
    data = path.read_text(encoding="utf-8")
    headers = list(re.finditer(r"^\s*(temperatures|heat generation) for set ALL and time\s+(\S+)\s*$", data, re.MULTILINE))
    if [m[1] for m in headers] != ["temperatures", "heat generation"]:
        raise EvidenceError("expected exactly one final temperature and heat-generation field")
    fields = []
    for i, header in enumerate(headers):
        try:
            if float(header[2]) != 1:
                raise EvidenceError("thermal result does not identify the final steady step")
            tail = data[header.end():headers[i+1].start() if i+1 < len(headers) else len(data)]
            values = {}
            for line in tail.splitlines():
                if not line.strip():
                    continue
                pieces = line.split()
                if len(pieces) != 2:
                    raise EvidenceError("malformed native nodal field row")
                node, value = int(pieces[0]), float(pieces[1])
                if node in values or node not in mesh.nodes or not np.isfinite(value):
                    raise EvidenceError("native nodal field contains repeated, unknown or nonfinite values")
                values[node] = value
        except (ValueError, OverflowError) as exc:
            raise EvidenceError(f"invalid native nodal field: {exc}") from exc
        if values.keys() != mesh.nodes.keys():
            raise EvidenceError("native nodal field does not cover every mesh node")
        fields.append(values)
    return fields[0], fields[1]


def measurements(output: Path, model: dict, run: dict) -> tuple[dict, Mesh]:
    for name in FILES:
        path = output / name
        if not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024 * 1024:
            raise EvidenceError(f"missing, empty or oversized native {name}")
    mesh = read_mesh(output / "model.msh", model)
    if (output / "model.geo").read_text(encoding="utf-8") != geometry(model, run["mesh_size_m"]):
        raise EvidenceError("native geometry script differs from the current model and mesh size")
    if (output / "thermal.inp").read_text(encoding="utf-8") != deck(mesh, model, run):
        raise EvidenceError("solver input differs from current geometry, material, load or boundary conditions")
    temperatures, heat = read_fields(output / "thermal.dat", mesh)
    rows = [line.split() for line in (output / "thermal.sta").read_text().splitlines() if re.match(r"^\s*\d", line)]
    if len(rows) != 1 or len(rows[0]) != 7 or rows[0][:2] != ["1", "1"]:
        raise EvidenceError("expected a completed single steady-state step")
    try:
        if float(rows[0][4]) != 1 or float(rows[0][5]) != 1:
            raise EvidenceError("steady-state step did not finish")
    except ValueError as exc:
        raise EvidenceError("invalid native step time") from exc
    power = run["power_w"]
    if "convection" in run:
        coefficient = run["convection"]["coefficient_w_m2k"]
        nodal, surface_heat = defaultdict(float), {}
        total_area = 0.0
        for group in sorted(run["convection"]["surfaces"]):
            surface_heat[group] = 0.0
            for _, _, face in mesh.surfaces[group]:
                a, b, c = (mesh.nodes[v] for v in face)
                area = float(np.linalg.norm(np.cross(b-a, c-a)) / 2)
                total_area += area
                rise_sum = sum(temperatures[v] for v in face)
                surface_heat[group] += coefficient * area * rise_sum / 3
                # C3D4 FILM uses one centroid integration point, not a consistent surface mass matrix.
                for node in face:
                    nodal[node] += coefficient * area * rise_sum / 9
        convected = sum(surface_heat.values())
        residual = sum(abs(heat[node] - (power * mesh.top_weights.get(node, 0) - nodal[node])) for node in mesh.nodes)
        balance = max(abs(convected-power), abs(sum(heat.values())), residual) / power
        if not np.isfinite(balance) or balance > 1e-5:
            raise EvidenceError("native convection heat balance does not close within 1e-5 relative error")
        mean_rise = sum(weight * temperatures[v] for v, weight in mesh.top_weights.items())
        ambient = temperature_offset(run)
        values = {
            "temperature_max_k": max(temperatures.values()) + ambient,
            "top_mean_k": mean_rise + ambient, "theta_top_k_w": mean_rise / power,
            "bottom_heat_w": surface_heat.get("bottom", 0.0),
            "convective_heat_w": convected, "convection_area_m2": total_area,
            "convection_heat_by_surface_w": surface_heat, "energy_relative_error": balance,
        }
        return values, mesh
    base = run["base_temperature_k"]
    # DAT temperatures use seven significant figures; honor that fixed native precision.
    temperature_resolution = max(abs(value) for value in temperatures.values()) * 1e-6
    if any(abs(temperatures[v]-base) > temperature_resolution for v in mesh.bottom):
        raise EvidenceError("prescribed bottom temperature is not satisfied")
    bottom = -sum(heat[v] for v in mesh.bottom)
    top = sum(heat[v] for v in mesh.top_weights)
    other = sum(abs(value) for v, value in heat.items() if v not in mesh.bottom and v not in mesh.top_weights)
    balance = max(abs(bottom-power), abs(top-power), other) / power
    if balance > 1e-5:
        raise EvidenceError("native heat balance does not close within 1e-5 relative error")
    mean = sum(weight * temperatures[v] for v, weight in mesh.top_weights.items())
    values = {
        "temperature_max_k": max(temperatures.values()), "top_mean_k": mean,
        "theta_top_k_w": (mean-base) / power, "bottom_heat_w": bottom,
        "energy_relative_error": balance,
    }
    return values, mesh


def comparable(path: Path) -> str:
    value = path.read_text(encoding="utf-8")
    if path.suffix == ".frd":
        return "\n".join(line for line in value.splitlines() if not line.startswith(("    1UDATE", "    1UTIME")))
    return value
