"""Run the FIFO's independent scoreboard in a new output directory."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .evidence import validate_simulation


def run_reference(root: Path) -> None:
    for tool in ("iverilog", "vvp"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} is required; install Icarus Verilog")
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("rtl", "tb", "verification/inputs"):
        (root / directory).mkdir(parents=True)
    examples = Path(__file__).parent / "skills/engineer_scripts"
    shutil.copyfile(examples / "stream_fifo.sv", root / "rtl/stream_fifo.sv")
    shutil.copyfile(examples / "stream_fifo_tb.sv", root / "tb/stream_fifo_tb.sv")
    matrix = [(width, depth, seed) for width in (1, 8) for depth in (1, 3, 8) for seed in (1, 7)]
    configurations = [f"width={w},depth={d},seed={s}" for w, d, s in matrix]
    cases = ["reset", "transfer", "stall", "full", "empty", "replacement"]
    plan = {
        "sources": ["rtl/stream_fifo.sv"],
        "testbenches": ["tb/stream_fifo_tb.sv"],
        "configurations": configurations,
        "cases": cases,
        "requirements": {f"FIFO {case} contract": [case] for case in cases},
    }
    (root / "verification/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")
    copies = {}
    for relative in ["verification/PLAN.json", *plan["sources"], *plan["testbenches"]]:
        snapshot = "verification/inputs/" + relative
        (root / snapshot).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, root / snapshot)
        copies[relative] = snapshot
    runs = []
    for (width, depth, seed), configuration in zip(matrix, configurations):
        name = f"w{width}_d{depth}_s{seed}"
        executable = f"verification/{name}.vvp"
        compile_command = [
            "iverilog", "-g2012", "-s", "stream_fifo_tb",
            f"-Pstream_fifo_tb.WIDTH={width}", f"-Pstream_fifo_tb.DEPTH={depth}",
            "-o", executable, *plan["sources"], *plan["testbenches"],
        ]
        compiled = subprocess.run(compile_command, cwd=root, capture_output=True, text=True, timeout=30)
        compile_log = f"verification/{name}.compile.log"
        (root / compile_log).write_text(compiled.stdout + compiled.stderr)
        compiled.check_returncode()
        command = ["vvp", executable, f"+SEED={seed}"]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
        log = f"verification/{name}.log"
        (root / log).write_text(result.stdout + result.stderr)
        result.check_returncode()
        runs.append({
            "configuration": configuration, "command": command, "exit_code": result.returncode,
            "log": log, "compile_command": compile_command, "compile_log": compile_log,
        })
    (root / "verification/RESULTS.json").write_text(json.dumps({"inputs": copies, "runs": runs}, indent=2) + "\n")
    validate_simulation(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    args = parser.parse_args()
    run_reference(args.output.resolve())
    print("PASS: 12 configurations; reset, transfer, stall, full, empty and replacement comparisons")


if __name__ == "__main__":
    main()
