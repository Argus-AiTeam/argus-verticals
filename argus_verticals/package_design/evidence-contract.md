# Canonical package thermal evidence

Work only on the requested scope. Specification needs `package/PLAN.json`;
model needs its declared package model files. Thermal work requires actual
native mesh/solver results. Review additionally requires `package/REVIEW.md`.
No physical package, fabricated component or unrelated design stage is implied.

The plan is a JSON object. This example is an **ideal reference**, not generic
material data or universal acceptance:

```json
{
  "objective": "Check an explicitly ideal two-layer conduction model",
  "requirements": {"resistance": "The model has 1.5 K/W series resistance"},
  "limitations": ["Perfect bonding; no physical qualification"],
  "models": ["design/stack.json"],
  "runs": [{
    "id": "nominal",
    "model": "design/stack.json",
    "mesh_size_m": 0.001,
    "power_w": 1,
    "base_temperature_k": 300,
    "checks": [{
      "id": "resistance",
      "requirement": "resistance",
      "metric": "theta_top_k_w",
      "unit": "K/W",
      "minimum": 1.499,
      "maximum": 1.501
    }]
  }],
  "convergence": []
}
```

Each model JSON explicitly declares `length_unit: "m"`, `temperature_unit: "K"`,
nonempty `source` and `validity`, a nonempty distinct `limitations` string list,
and `layers` ordered **bottom to top**:

```json
{
  "length_unit": "m",
  "temperature_unit": "K",
  "source": "Original ideal reference constants",
  "validity": "Steady conduction through two perfectly bonded solids",
  "limitations": ["Not a measured commercial package"],
  "layers": [
    {"id": "substrate", "size_xy_m": [0.01, 0.01], "thickness_m": 0.001,
     "conductivity_w_mk": 10, "material_source": "Chosen reference constant"},
    {"id": "die", "size_xy_m": [0.01, 0.01], "thickness_m": 0.001,
     "conductivity_w_mk": 20, "material_source": "Chosen reference constant"}
  ]
}
```

Layers are axis-aligned rectangular solids centred at x=y=0, stacked without
gaps in +z. They may have different lateral dimensions, allowing a smaller
die on a larger substrate and actual three-dimensional spreading. Contact is
perfectly bonded with shared conformal nodes and zero interface resistance.
Each material is homogeneous with positive constant isotropic conductivity.

In the original mode, the entire bottom face is fixed at `base_temperature_k`.
`power_w` is positive
total power applied **uniformly to the entire uppermost face**, not volumetric
die dissipation. All other exposed surfaces are adiabatic. The runner integrates
the uniform surface flux over native triangular faces: each triangle supplies
one third of its power to each of its nodes. This conserves the original total
power; equal power per node would not represent uniform surface flux.

### Explicit convection boundary

Alternatively, **omit** `base_temperature_k` and supply this run object:

```json
"convection": {
  "ambient_temperature_k": 300,
  "coefficient_w_m2k": 1000,
  "surfaces": ["bottom", "top", "other_exposed"],
  "source": "Explicit ideal reference coefficient, not predicted airflow"
}
```

The four keys are required; additional keys are rejected. Ambient is 1-2000 K;
the positive, constant coefficient is 1e-3 to 1e6 W/(m2 K).
`surfaces` is a nonempty list without duplicates. `bottom` and `top` mean the
entire lowest and uppermost faces; `other_exposed` means all other exterior
faces, including stepped ledges and overhang undersides. The groups do not
overlap, bonded interfaces never receive film, and unselected faces are
adiabatic. Source power remains uniform on the top, even when top convection
is also selected. A coefficient requires a nonempty source; it is an imposed
assumption, not a solved airflow correlation.

The solver applies native `*FILM`, element ID, F1-F4 face, sink temperature
and coefficient. Tetrahedron faces follow CalculiX's local-node numbering:
1-2-3, 1-4-2, 2-4-3, 3-4-1. For constant properties and a single common
ambient, the native unknown is the rise T-Tambient with zero film sink.
This exact linear change of variable preserves tiny rises in finite-precision
DAT output. Native DAT/FRD NT is **rise**, not absolute Kelvin; each run records
`temperature_reference_k` equal to the original ambient. Add it to native NT
for physical temperature. Fixed-bottom runs retain absolute NT and reference 0.
Do not relabel raw fields or subtract two nearly equal absolute temperatures
to calculate convection resistance.

Native total heat is integrated as h*A*mean(face rise). For nodal RFL checks,
C3D4 uses one centroid integration point: each face contributes one third of
that extraction to each vertex. At shared vertices, sum every incident film
face and subtract from the applied top nodal power. RFL is the resulting net
external nodal load, not conduction flux alone. Summing bottom-node RFL would
incorrectly include side cooling or top loading; bottom heat in convection
mode is instead integrated over bottom **faces** only.

## Scope, metrics and refinement

`models` declares up to eight paths; thermal scope reads only selected runs'
model files. Model scope checks every declared model. All inputs are
project-relative and outside `package/results`. Each model has 1-8 layers.
IDs use a lowercase letter followed by at most 31 lowercase letters, digits
or underscores. Numeric fields reject booleans and nonfinite values.

Supported dimensions are 1e-5 to 0.1 metres, total thickness <=0.1 m,
conductivity 1e-3 to 1e4 W/(m K), base temperature 1-2000 K and positive
power 1e-6 to 1e4 W. Mesh size is 1e-5 to 0.1 m and passes a conservative
element-count estimate. These are execution bounds, not physical plausibility
approval. A native mesh is limited to 20000 nodes, 100000 total elements and
32 MiB. Only linear tetrahedral volume elements and selected triangular
top/bottom boundary elements are accepted.

Declare 1-8 `runs`, each with 1-32 checks. `requirements` maps IDs to nonempty
descriptions; every requirement needs a check, and every check references a
known requirement. `limitations` is a nonempty distinct string list.
Each check has `id`, `requirement`, `metric`, `unit`, `minimum`, `maximum`.
Bounds must be independently chosen before execution and cannot be loosened
to make a result pass.

| Metric | Unit | Meaning |
|---|---|---|
| `temperature_max_k` | `K` | Maximum physical nodal temperature, including the declared reference |
| `top_mean_k` | `K` | Area-weighted mean temperature of the heated face |
| `theta_top_k_w` | `K/W` | Heated-face mean rise above prescribed bottom or ambient / applied power |
| `bottom_heat_w` | `W` | Heat leaving the bottom face; zero if bottom is adiabatic |
| `convective_heat_w` | `W` | Total outward film heat, convection mode only |
| `convection_area_m2` | `m2` | Total selected exterior film area, convection mode only |
| `energy_relative_error` | `1` | Worst relative heat imbalance, including nodal native film-load residual |

The model resistance is **not automatically JEDEC theta-JA or theta-JC**.
Independently of optional checks, native heat balance must close within 1e-5
relative error. Fixed-bottom temperatures must match the imposed value within
the fixed native DAT output precision. Original engineering bounds are never
adjusted for that precision; choose an appropriate supported measurement.

For different-width layers and **every convection run**, a refinement comparison is required:

```json
{"coarse": "coarse_run", "fine": "fine_run",
 "metric": "temperature_max_k", "max_delta": 0.15}
```

Place these objects in the plan's `convergence` list (up to eight). Both runs
must use the same model, power and complete boundary specification (including
convection source, ambient, coefficient and surface list); fine mesh size must be
<=80% of coarse and actually produce more native tetrahedra. Allowed comparison
metrics are the two temperatures or `theta_top_k_w`. `max_delta` is an absolute
difference in that metric's unit. Every spreading run must appear in a pair.
Two meshes establish only the declared agreement, not a proven error bound.
Returned measurements also include `convection_heat_by_surface_w` for the
selected groups; these are independently recomputed, not trusted saved summaries.

## Native execution and records

Install Gmsh >=4.12 within 4.x and CalculiX `ccx` >=2.21 within 2.x,
plus the declared numpy dependency. The validated initial tools are Gmsh
4.12.1 and CalculiX 2.21. This is native `.geo`/MSH meshing and `.inp` thermal
execution, not a Python replacement for either solver.

The runner refuses existing `package/results`, copies the plan and selected
model files under `package/results/inputs`, isolates native user configuration
and uses one thread. It preserves each run's geometry, mesh, solver input,
DAT nodal fields, STA completion, FRD visualization fields, logs and exact
command records. `package/results/RESULTS.json` is written by the runner:
`operation: "gmsh+calculix"`, execution `status`, actual `versions`,
input/output copy maps and ordered run IDs with `temperature_reference_k` and native command rows
(`tool`, `command`, `cwd`, `log`, `exit_code`). Failed attempts remain intact.

The checker rejects stale/self/hardlinked copies, wrong commands, invalid
mesh volumes/interfaces/boundaries, missing or nonfinite fields and failed
original bounds. It independently re-executes both tools in a temporary
directory and compares every retained native file; only FRD creation date/time
headers are omitted. It never changes the project. A tool-version change needs
a new run. CalculiX input numbers use bounded-width scientific notation;
DAT temperatures have seven significant figures, not arbitrary precision.
Actual solver execution requires exit 0 **and** finished-job output without
native errors. A nonzero solver exit is never accepted merely because output
files or a finished-job message exist.

## Explicit exclusions

No arbitrary CAD import, lateral offsets, contact resistance, voids,
anisotropic/temperature-dependent conductivity, transient thermal capacitance,
radiation, CFD, electrical parasitics, stress, warpage, fatigue,
delamination, yield, measured-device calibration or qualification is executed.
Mixed fixed-temperature/convection cooling, multiple ambients, local face
patches and nonuniform or temperature-dependent convection coefficients are
not supported.
Those subjects remain important knowledge and must not be claimed as solved.
No commercial EDA tool, PDK, foundry process or manufacturing order is implied.
