"""Run original ideal reference studies whose answers follow from independent scalar equations.

Use it to confirm that the installed Gmsh/CalculiX reproduce series resistances and conserve
heat; the target directory must not exist yet.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import EvidenceError
from run_analysis import run_analysis


def prepare_conduction(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    (root / "design").mkdir()
    (root / "package").mkdir()
    base = {
        "length_unit": "m", "temperature_unit": "K",
        "source": "Original ideal solid reference with explicitly chosen constants.",
        "validity": "Steady conduction, perfect bonding and constant isotropic conductivity.",
        "limitations": ["No actual commercial material, interface resistance, convection, radiation or measured package claim."],
    }

    def layer(identity, conductivity, width=0.01):
        return {
            "id": identity, "size_xy_m": [width, width], "thickness_m": 0.001,
            "conductivity_w_mk": conductivity, "material_source": "Explicit ideal reference constant, not measured material data.",
        }

    models = {
        "slab": [layer("slab", 10)],
        "stack": [layer("substrate", 10), layer("die", 20)],
        "spreading": [layer("substrate", 10), layer("die", 20, 0.005)],
    }
    for identity, layers in models.items():
        (root / f"design/{identity}.json").write_text(json.dumps({**base, "layers": layers}, indent=2) + "\n")

    def run(identity, model, size, resistance):
        checks = [{
            "id": "maximum", "requirement": model, "metric": "temperature_max_k", "unit": "K",
            "minimum": 300+resistance-0.001 if resistance is not None else 300.5,
            "maximum": 300+resistance+0.001 if resistance is not None else 310,
        }]
        if resistance is not None:
            checks.append({"id": "resistance", "requirement": model, "metric": "theta_top_k_w", "unit": "K/W",
                           "minimum": resistance-0.001, "maximum": resistance+0.001})
        return {"id": identity, "model": f"design/{model}.json", "mesh_size_m": size,
                "power_w": 1, "base_temperature_k": 300, "checks": checks}

    plan = {
        "objective": "Verify native heat conduction against independent scalar equations and mesh-refined lateral spreading.",
        "requirements": {"slab": "R = thickness / (k A) = 1 K/W.", "stack": "R = sum(thickness / (k A)) = 1.5 K/W.",
                         "spreading": "Bound the original stepped die/substrate model and demonstrate mesh refinement."},
        "limitations": base["limitations"], "models": [f"design/{name}.json" for name in models],
        "runs": [run("slab", "slab", 0.001, 1), run("stack", "stack", 0.001, 1.5),
                 run("coarse", "spreading", 0.001, None), run("fine", "spreading", 0.0007, None)],
        "convergence": [{"coarse": "coarse", "fine": "fine", "metric": "temperature_max_k", "max_delta": 0.15}],
    }
    (root / "package/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def prepare_convection(root: Path) -> None:
    prepare_conduction(root)
    limitations = [
        "Ideal bonded solids and prescribed uniform film coefficient; not measured package or material data.",
        "No resolved airflow, radiation, contact resistance, transient, mechanics or physical qualification.",
    ]
    for path in (root / "design").glob("*.json"):
        model = json.loads(path.read_text(encoding="utf-8"))
        model["limitations"] = limitations
        path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    runs, comparisons = [], []
    for identity, model, surfaces, size, resistance in (
        ("bottom", "slab", ["bottom"], 0.002, 11),
        ("top", "slab", ["top"], 0.002, 10),
        ("exposed", "spreading", ["bottom", "top", "other_exposed"], 0.001, None),
    ):
        for resolution, scale in (("coarse", 1), ("fine", 0.7)):
            checks = [
                {"id": "maximum", "requirement": identity, "metric": "temperature_max_k", "unit": "K",
                 "minimum": 300+resistance-0.001 if resistance is not None else 303,
                 "maximum": 300+resistance+0.001 if resistance is not None else 320},
                {"id": "heat", "requirement": identity, "metric": "convective_heat_w", "unit": "W",
                 "minimum": 0.99999, "maximum": 1.00001},
            ]
            if resistance is not None:
                checks.append({"id": "resistance", "requirement": identity, "metric": "theta_top_k_w", "unit": "K/W",
                               "minimum": resistance-0.001, "maximum": resistance+0.001})
            runs.append({
                "id": f"{identity}_{resolution}", "model": f"design/{model}.json",
                "mesh_size_m": size*scale, "power_w": 1,
                "convection": {"ambient_temperature_k": 300, "coefficient_w_m2k": 1000,
                               "surfaces": surfaces, "source": "Explicit ideal film reference, not a predicted convection coefficient."},
                "checks": checks,
            })
        comparisons.append({"coarse": f"{identity}_coarse", "fine": f"{identity}_fine",
                            "metric": "temperature_max_k", "max_delta": 0.001 if resistance is not None else 0.25})
    plan = {
        "objective": "Check native prescribed convection, conserved heat and declared numerical refinement.",
        "requirements": {
            "bottom": "Bottom convection in series with slab conduction gives 1/(h A)+t/(k A)=11 K/W.",
            "top": "Heating and convection on the same top surface gives uniform temperature rise P/(h A)=10 K.",
            "exposed": "All exterior faces, including stepped ledges, exchange heat; original power is conserved under refinement.",
        },
        "limitations": limitations, "models": ["design/slab.json", "design/spreading.json"],
        "runs": runs, "convergence": comparisons,
    }
    (root / "package/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path, help="new directory to create the reference project in")
    parser.add_argument("--convection", action="store_true",
                        help="run the six prescribed-convection studies instead of the four fixed-bottom ones")
    args = parser.parse_args()
    try:
        (prepare_convection if args.convection else prepare_conduction)(args.project)
        measured = run_analysis(args.project)
    except (EvidenceError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    print(json.dumps(measured, indent=2))
    print("PASS: native results match the independent reference equations and declared refinement")


if __name__ == "__main__":
    main()
