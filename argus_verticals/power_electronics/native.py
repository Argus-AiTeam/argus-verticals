"""Generate bounded circuits and execute ngspice with native resource limits."""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.hardware.spice.raw import MAX_RAW_BYTES, read_plot

FILES = ("model.cir", "wave.raw", "ngspice.log", "console.log")
COMMAND = ("ngspice", "-n", "-b", "-r", "wave.raw", "-o", "ngspice.log", "model.cir")
TIMEOUT_SECONDS = 120
MAX_OUTPUT_BYTES = MAX_RAW_BYTES


def version() -> str:
    try:
        result = subprocess.run(["ngspice", "-n", "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"native ngspice is required: {exc}") from exc
    match = re.search(r"\bngspice-(\d+(?:\.\d+)?)\b", result.stdout + result.stderr)
    if result.returncode != 0 or match is None or int(match[1].split(".")[0]) < 42:
        raise EvidenceError("this adapter requires native ngspice >=42")
    return match[1]


def deck(model: dict, run: dict) -> str:
    def n(value):
        return format(value, ".16g")

    period = 1 / run["frequency_hz"]
    edge = period / 1000
    g0 = 1 / run["load_resistance_ohm"]
    if "load_step" in run:
        step = run["load_step"]
        g1 = 1 / step["resistance_ohm"]
        conductance = f"PWL(0 {n(g0)} {n(step['time_s'])} {n(g0)} {n(step['time_s']+step['transition_s'])} {n(g1)} {n(run['duration_s'])} {n(g1)})"
    else:
        conductance = f"DC {n(g0)}"
    wiring = (
        ["Smain in switch_mid pwm 0 SWMAIN", "Vswitch switch_mid sw 0",
         "Drect 0 rect_mid RECT", "Vrect rect_mid sw 0",
         f"Rind sw lin {n(model['inductor_resistance_ohm'])}",
         f"Lpower lin out {n(model['inductance_h'])} IC=0"]
        if model["topology"] == "buck" else
        [f"Rind in lin {n(model['inductor_resistance_ohm'])}",
         f"Lpower lin sw {n(model['inductance_h'])} IC=0",
         "Smain sw switch_mid pwm 0 SWMAIN", "Vswitch switch_mid 0 0",
         "Drect sw rect_mid RECT", "Vrect rect_mid out 0"]
    )
    return "\n".join([
        f"Argus bounded {model['topology']} converter",
        f"Vin in 0 DC {n(run['input_voltage_v'])}",
        f"Vpwm pwm 0 PULSE(0 1 0 {n(edge)} {n(edge)} {n(run['duty_cycle']*period-edge)} {n(period)})",
        f".model SWMAIN SW(Ron={n(model['switch_on_resistance_ohm'])} Roff={n(model['switch_off_resistance_ohm'])} Vt=0.5 Vh=0)",
        f".model RECT D(Is={n(model['diode_saturation_current_a'])} N={n(model['diode_emission'])} Rs={n(model['diode_resistance_ohm'])} Cjo=0 Tt=0)",
        *wiring, f"Rcap out cap {n(model['capacitor_esr_ohm'])}",
        f"Cout cap 0 {n(model['capacitance_f'])} IC=0",
        "Vload out load 0", f"Vconductance conductance 0 {conductance}",
        "Bload load 0 I=v(load)*v(conductance)",
        ".options reltol=1e-6 abstol=1e-9 vntol=1e-8 chgtol=1e-14 method=gear maxord=2 tnom=27",
        f".temp {n(model['temperature_c'])}",
        ".save v(in) v(out) v(cap) v(sw) v(pwm) v(conductance) i(vin) i(lpower) i(vswitch) i(vrect) i(vload)",
        f".tran {n(run['max_step_s'])} {n(run['duration_s'])} 0 {n(run['max_step_s'])} uic",
        ".end", "",
    ])


def check_output(output: Path, model: dict, run: dict):
    for name in FILES:
        path = output / name
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_RAW_BYTES:
            raise EvidenceError(f"missing, empty or oversized native {name}")
    if (output / "model.cir").read_text() != deck(model, run):
        raise EvidenceError("native circuit differs from the current model or study")
    log = (output / "ngspice.log").read_text()
    if re.search(r"^\s*(?:Error|Fatal|Warning|doAnalyses:)", log, re.MULTILINE | re.IGNORECASE):
        raise EvidenceError("ngspice reported a diagnostic; inspect the preserved native log")
    count = re.search(r"No\. of Data Rows\s*:\s*(\d+)", log)
    plot = read_plot(output / "wave.raw", "tran")
    if count is None or int(count[1]) != len(plot.rows):
        raise EvidenceError("native completion count differs from the saved transient waveform")
    if abs(plot.rows[-1][0].real - run["duration_s"]) > run["duration_s"] * 1e-12:
        raise EvidenceError("native transient did not reach the requested final time")
    return plot


def execute(model: dict, run: dict, output: Path, *, save=None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    (output / "model.cir").write_text(deck(model, run), encoding="ascii")
    home = output / "config"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPICE", "NGSPICE"))}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home), SPICE_ASCIIRAWFILE="1", LC_ALL="C", OMP_NUM_THREADS="1")
    row = {"command": list(COMMAND), "cwd": str(output), "log": str(output / "ngspice.log"), "exit_code": None}
    if save:
        save(row)
    stopped = ""
    try:
        with (output / "console.log").open("w") as console:
            with subprocess.Popen(COMMAND, cwd=output, env=env, stdout=console, stderr=subprocess.STDOUT) as process:
                deadline = time.monotonic() + TIMEOUT_SECONDS
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        stopped = f"native simulation exceeded {TIMEOUT_SECONDS:g} seconds"
                    elif sum((output / name).stat().st_size for name in FILES if (output / name).exists()) > MAX_OUTPUT_BYTES:
                        stopped = f"native output exceeded {MAX_OUTPUT_BYTES} bytes"
                    if stopped:
                        process.kill()
                        break
                    time.sleep(0.05)
                row["exit_code"] = process.wait()
    except OSError as exc:
        raise EvidenceError(f"ngspice execution failed: {exc}") from exc
    if save:
        save(row)
    if stopped or row["exit_code"] != 0:
        raise EvidenceError(f"{stopped or 'ngspice failed'}; inspect {output}")
    check_output(output, model, run)
    return row
