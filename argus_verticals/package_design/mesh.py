"""Generate original Gmsh geometry and verify conformal tetrahedral native meshes."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

from argus_verticals.hardware.shared.evidence import EvidenceError

from .model import temperature_offset

TET_FACES = ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0))


def geometry(model: dict, size: float) -> str:
    lines = ['SetFactory("OpenCASCADE");']
    z, bounds = 0.0, []
    for i, layer in enumerate(model["layers"], 1):
        x, y = layer["size_xy_m"]
        h = layer["thickness_m"]
        lines.append(f"Box({i}) = {{{-x/2:.17g},{-y/2:.17g},{z:.17g},{x:.17g},{y:.17g},{h:.17g}}};")
        bounds.append((-x/2, -y/2, z, x/2, y/2, z+h))
        z += h
    if len(bounds) > 1:
        others = ",".join(str(i) for i in range(2, len(bounds)+1))
        lines.append(f"volumes() = BooleanFragments{{Volume{{1}}; Delete;}}{{Volume{{{others}}}; Delete;}};")
    epsilon = 2e-7

    def box(values):
        return ",".join(f"{value + (-epsilon if i < 3 else epsilon):.17g}" for i, value in enumerate(values))

    for i, values in enumerate(bounds, 1):
        lines.append(f'Physical Volume("layer_{i}",{i}) = Volume In BoundingBox{{{box(values)}}};')
    first, last = bounds[0], bounds[-1]
    for label, tag, values in (
        ("bottom", 101, (*first[:3], first[3], first[4], first[2])),
        ("top", 102, (last[0], last[1], last[5], *last[3:])),
    ):
        lines.append(f'Physical Surface("{label}",{tag}) = Surface In BoundingBox{{{box(values)}}};')
    lines.extend([
        f"Mesh.MeshSizeMin = {size:.17g};", f"Mesh.MeshSizeMax = {size:.17g};",
        "Mesh.ElementOrder = 1;", "Mesh.Algorithm = 6;", "Mesh.Algorithm3D = 1;",
        "Mesh.RandomSeed = 1;", "Mesh.Binary = 0;", "Mesh.MshFileVersion = 2.2;",
    ])
    return "\n".join(lines) + "\n"


@dataclass
class Mesh:
    nodes: dict[int, np.ndarray]
    elements: dict[int, tuple[int, tuple[int, ...]]]
    bottom: set[int]
    top_weights: dict[int, float]
    surfaces: dict[str, list[tuple[int, int, tuple[int, ...]]]]


def read_mesh(path: Path, model: dict) -> Mesh:
    if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise EvidenceError("native mesh is missing or exceeds 32 MiB")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines[:3] != ["$MeshFormat", "2.2 0 8", "$EndMeshFormat"]:
            raise EvidenceError("only native ASCII MSH 2.2 double coordinates are supported")

        def section(name, limit):
            if lines.count("$" + name) != 1:
                raise EvidenceError(f"mesh needs exactly one {name} section")
            start = lines.index("$" + name)
            count = int(lines[start+1])
            if not 1 <= count <= limit or lines[start+2+count] != "$End" + name:
                raise EvidenceError(f"invalid native {name} count")
            return lines[start+2:start+2+count]

        nodes = {}
        for line in section("Nodes", 20000):
            fields = line.split()
            identity = int(fields[0])
            xyz = np.array([float(v) for v in fields[1:]])
            if identity <= 0 or identity in nodes or xyz.shape != (3,) or not np.all(np.isfinite(xyz)):
                raise EvidenceError("invalid, repeated or nonfinite mesh node")
            nodes[identity] = xyz
        elements, triangles, identities = {}, {101: [], 102: []}, set()
        for line in section("Elements", 100000):
            fields = [int(v) for v in line.split()]
            identity, kind, tags = fields[:3]
            if identity <= 0 or identity in identities or tags < 2 or len(fields) < 3+tags:
                raise EvidenceError("invalid or repeated native mesh element")
            identities.add(identity)
            physical, vertices = fields[3], tuple(fields[3+tags:])
            if len(set(vertices)) != len(vertices) or not set(vertices) <= nodes.keys():
                raise EvidenceError("element nodes are repeated or missing")
            if kind == 4 and len(vertices) == 4 and 1 <= physical <= len(model["layers"]):
                elements[identity] = (physical, vertices)
            elif kind == 2 and len(vertices) == 3 and physical in triangles:
                triangles[physical].append(tuple(sorted(vertices)))
            else:
                raise EvidenceError("mesh contains unsupported elements or physical groups")
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise EvidenceError(f"cannot read native mesh: {exc}") from exc
    if not elements or set().union(*(set(v) for _, v in elements.values())) != set(nodes):
        raise EvidenceError("mesh has no volume elements or contains isolated nodes")
    z = 0.0
    bounds = {}
    for i, layer in enumerate(model["layers"], 1):
        x, y = layer["size_xy_m"]
        bounds[i] = (np.array([-x/2, -y/2, z]), np.array([x/2, y/2, z+layer["thickness_m"]]))
        z += layer["thickness_m"]
    volume, faces, tet_ids = defaultdict(float), defaultdict(list), set()
    for physical, vertex in elements.values():
        sorted_vertex = tuple(sorted(vertex))
        if sorted_vertex in tet_ids:
            raise EvidenceError("duplicate tetrahedron")
        tet_ids.add(sorted_vertex)
        points = np.array([nodes[v] for v in vertex])
        low, high = bounds[physical]
        if np.any(points < low-1e-12) or np.any(points > high+1e-12):
            raise EvidenceError("tetrahedron disagrees with its material-layer geometry")
        determinant = np.linalg.det((points[1:] - points[0]).T)
        if not np.isfinite(determinant) or determinant <= 0:
            raise EvidenceError("inverted or degenerate tetrahedron")
        volume[physical] += determinant / 6
        for face in combinations(vertex, 3):
            faces[tuple(sorted(face))].append(physical)
    for i, layer in enumerate(model["layers"], 1):
        expected = np.prod(layer["size_xy_m"]) * layer["thickness_m"]
        if not np.isclose(volume[i], expected, rtol=1e-8, atol=0):
            raise EvidenceError("native mesh layer volume disagrees with the declared solid")
    if any(len(owners) not in (1, 2) for owners in faces.values()):
        raise EvidenceError("nonmanifold native mesh")

    def area(face):
        a, b, c = (nodes[v] for v in face)
        return float(np.linalg.norm(np.cross(b-a, c-a)) / 2)

    interfaces = defaultdict(float)
    expected_surfaces = {101: set(), 102: set()}
    for face, owners in faces.items():
        if len(owners) == 2 and owners[0] != owners[1]:
            interfaces[tuple(sorted(owners))] += area(face)
        if len(owners) == 1:
            if all(abs(nodes[v][2]) <= 1e-12 for v in face):
                expected_surfaces[101].add(face)
            if all(abs(nodes[v][2]-z) <= 1e-12 for v in face):
                expected_surfaces[102].add(face)
    for i, (lower, upper) in enumerate(zip(model["layers"], model["layers"][1:]), 1):
        expected = np.prod(np.minimum(lower["size_xy_m"], upper["size_xy_m"]))
        if not np.isclose(interfaces[(i, i+1)], expected, rtol=1e-8, atol=0):
            raise EvidenceError("material interface is not conformal and perfectly bonded")
    weights, bottom = defaultdict(float), set()
    for tag, rows in triangles.items():
        if not rows or any(count != 1 for count in Counter(rows).values()) or set(rows) != expected_surfaces[tag]:
            raise EvidenceError("top/bottom physical triangles do not match the native solid boundary")
        expected = float(np.prod(model["layers"][0 if tag == 101 else -1]["size_xy_m"]))
        if not np.isclose(sum(area(face) for face in rows), expected, rtol=1e-8, atol=0):
            raise EvidenceError("thermal boundary area disagrees with geometry")
        for face in rows:
            if tag == 101:
                bottom.update(face)
            else:
                for vertex in face:
                    weights[vertex] += area(face) / (3 * expected)
    if bottom & weights.keys():
        raise EvidenceError("heat input and prescribed-temperature nodes overlap")
    surfaces = {"bottom": [], "top": [], "other_exposed": []}
    for element, (_, vertex) in elements.items():
        for label, indices in enumerate(TET_FACES, 1):
            face = tuple(vertex[i] for i in indices)
            key = tuple(sorted(face))
            if len(faces[key]) != 1:
                continue
            group = "bottom" if key in expected_surfaces[101] else "top" if key in expected_surfaces[102] else "other_exposed"
            surfaces[group].append((element, label, face))
    expected_area = sum(
        2 * (x*y + (x+y)*layer["thickness_m"])
        for layer in model["layers"] for x, y in [layer["size_xy_m"]]
    ) - 2 * sum(interfaces.values())
    actual_area = sum(area(face) for rows in surfaces.values() for _, _, face in rows)
    if not np.isclose(actual_area, expected_area, rtol=1e-8, atol=0):
        raise EvidenceError("exposed native surface area disagrees with the original stacked solids")
    return Mesh(nodes, elements, bottom, dict(weights), surfaces)


def deck(mesh: Mesh, model: dict, run: dict) -> str:
    lines = ["*HEADING", "Argus constant-conductivity package thermal study", "*NODE,NSET=ALL"]
    # CalculiX numeric fields have a bounded width; 17-digit general format can exceed it.
    lines.extend(f"{key}," + ",".join(f"{v:.12e}" for v in xyz) for key, xyz in mesh.nodes.items())
    for physical, layer in enumerate(model["layers"], 1):
        lines.append(f"*ELEMENT,TYPE=C3D4,ELSET=L{physical}")
        lines.extend(f"{key}," + ",".join(map(str, vertex)) for key, (owner, vertex) in mesh.elements.items() if owner == physical)
        lines.extend([
            f"*MATERIAL,NAME=M{physical}", "*CONDUCTIVITY", f"{layer['conductivity_w_mk']:.12e}",
            f"*SOLID SECTION,ELSET=L{physical},MATERIAL=M{physical}",
        ])
    convection = run.get("convection")
    temperature = f"{0 if convection else run['base_temperature_k']:.12e}"
    lines.extend(["*NSET,NSET=BOTTOM", *map(str, sorted(mesh.bottom)),
                  "*INITIAL CONDITIONS,TYPE=TEMPERATURE", f"ALL,{temperature}",
                  "*STEP", "*HEAT TRANSFER,STEADY STATE", "1,1"])
    if convection:
        lines.extend([
            f"** Native NT is temperature rise above uniform ambient {temperature_offset(run):.12e} K",
            "*FILM",
        ])
        for group in sorted(convection["surfaces"]):
            for element, label, _ in mesh.surfaces[group]:
                lines.append(f"{element},F{label},0.,{convection['coefficient_w_m2k']:.12e}")
    else:
        lines.extend(["*BOUNDARY", f"BOTTOM,11,11,{temperature}"])
    lines.append("*CFLUX")
    # Integrating a uniform flux over each linear triangle gives area/3 per vertex.
    lines.extend(f"{v},11,{weight * run['power_w']:.12e}" for v, weight in sorted(mesh.top_weights.items()))
    lines.extend(["*NODE PRINT,NSET=ALL", "NT,RFL", "*NODE FILE", "NT,RFL", "*END STEP"])
    return "\n".join(lines) + "\n"
