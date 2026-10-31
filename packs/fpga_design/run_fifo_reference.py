"""Run the reference FIFO's independent scoreboard over 12 configurations in a new directory.

Adapted from Argus digital_circuit verification; needs Icarus Verilog (iverilog, vvp) and uses
evidence.py and fifo_reference/ from this folder.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evidence import validate_simulation  # noqa: E402


def run_reference(root: Path) -> None:
    for tool in ("iverilog", "vvp"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} is required; install Icarus Verilog")
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("rtl", "tb", "verification/inputs"):
        (root / directory).mkdir(parents=True)
    shutil.copyfile(HERE / "fifo_reference/stream_fifo.sv", root / "rtl/stream_fifo.sv")
    shutil.copyfile(HERE / "fifo_reference/stream_fifo_tb.sv", root / "tb/stream_fifo_tb.sv")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    args = parser.parse_args()
    try:
        run_reference(args.output.resolve())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: 12 configurations; reset, transfer, stall, full, empty and replacement comparisons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
