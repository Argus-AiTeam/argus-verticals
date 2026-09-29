"""Check independent series-resistance equations and a refined die/substrate spreading case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_analysis import run_analysis


def prepare_reference(root: Path) -> None:
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
