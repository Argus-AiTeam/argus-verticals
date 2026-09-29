# Power electronics

Independent domain `hardware / power_electronics`, with no analog or digital
workflow inheritance. `vertical.json` declares its numpy dependency and
bundled shared helpers. Sixteen skills cover conversion, devices/drivers,
magnetics, passive filters, control, protection, losses/thermal constraints,
layout/EMI, isolation and drives, with role-specific decision and review rules.

## Executable scope

Actual ngspice Buck/Boost startup, switching ripple and resistive-load changes:
open-loop PWM, linear L/C with explicit series resistance, a finite-resistance
controlled switch and native memoryless diode. Observe selected time windows,
check source/load/loss/stored-energy balance and compare refined time steps.
These are deliberately illustrative circuit models, not measured commercial
parts or hardware approval.

| Profile | Stages |
|---|---|
| `specification` | specification |
| `model` | model |
| `simulation` | simulation |
| `review` | simulation, review |
| `full` | specification, model, simulation, review |

Custom scopes retain `review`'s simulation obligation without forcing unrelated
requirements or model stages. Specification/model stages do not execute a solver.
All roles receive the same [canonical contract](evidence-contract.md).

```bash
pip install -e ".[power]"
python -m argus_verticals.power_electronics.run_reference /tmp/new-power-reference
python -m argus_verticals.power_electronics.run_robustness_reference /tmp/new-power-envelope
python -m argus_verticals.power_electronics.run_robustness_reference /tmp/new-power-diagnosis --goal diagnose --tight
python -m argus_verticals.power_electronics.run_analysis /path/to/project
```

Install native ngspice >=42 separately. Store-installed roles use the exact
interpreter/provider-loader commands in their context, rather than assuming an
editable package is importable in a child process. The shared native reader
is `argus_verticals.hardware.spice.raw`; file/copy checks are in
`argus_verticals.hardware.shared`. Neither imports an analog workflow.

`model.py` validates physical inputs and scopes; `native.py` writes bounded
circuits and monitors real processes; `waveform.py` performs time-weighted
measurements; `evidence.py` enforces original limits and independent replay.
Execution preserves failed attempts and refuses existing results.

Version 0.2 adds an optional separately declared operating specification.
`study.py` resolves a fixed common design plus the full Cartesian product of
input/load/temperature/component samples, including nominal; `robustness.py`
executes and independently replays every coarse/fine pair, then computes
coverage, all original limit failures and required numerical headroom.
The original plan format and scoped workflow remain compatible.

The supplied specification fixes `diagnose` or `design`. A valid complete
diagnosis may conclude that the circuit fails; a design task must satisfy all
sampled conditions and margins. Missing/invalid evidence or failed refinement
cannot complete either. Read both `task_accepted` and engineering `status`
in `power/results/ASSESSMENT.json`; task completion alone is not design approval.
The new reference demonstrates a passing finite design and a nominal-pass,
corner-fail diagnosis under separate original specifications.

At most 17 scenarios (including nominal) and 1,500,000 estimated points are
supported. Every execution/replay phase has a 600-second limit; total native
outputs are bounded to 512 MiB, excluding their retained copies. Individual
native calls remain bounded to 120 seconds and 64 MiB.
Finite sampled coverage is not a continuous guarantee, statistical yield or
physical qualification. Temperature changes the modeled diode; unspecified
temperature coefficients and electrothermal feedback are not invented.

The original reference covers both converter types, startup, an actual
conductance ramp, pre/post-load steady intervals and smaller maximum time
steps. Independent averaged CCM equations include winding/switch resistance
and a Shockley diode approximation at 27 degC; they bound mean voltage and
inductor ripple, not the complete transient waveform. Actual steady-cycle
checks establish that the selected intervals are sufficiently periodic.

Numerical methods matter: a prototype with a piecewise ideal rectifier and
trapezoidal integration suffered tiny-step collapse near discontinuous
conduction. The production model uses the declared native diode and Gear
integration, with explicit time/size bounds and time-step sensitivity checks.
Changing physical assumptions to cure a failure requires a new documented model,
not a silent replacement of a user's device data.

No arbitrary netlists, feedback synthesis, charge/recovery effects, magnetic
saturation, core loss, EMI qualification, real efficiency or physical operation
is claimed. Broader topics remain knowledge until they have separate native
interfaces, evidence interpretation and executable references.
