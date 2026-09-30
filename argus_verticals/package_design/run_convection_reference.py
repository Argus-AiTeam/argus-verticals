"""Compare explicit native convection with scalar thermal resistances and mesh refinement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_analysis import run_analysis
from .run_reference import prepare_reference as prepare_conduction


def prepare_reference(root: Path) -> None:
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


def run_reference(root: Path) -> dict:
    prepare_reference(root)
    return run_analysis(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_reference(args.project), indent=2))


if __name__ == "__main__":
    main()
