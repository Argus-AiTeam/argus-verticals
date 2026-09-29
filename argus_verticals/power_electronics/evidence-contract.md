# Canonical power-converter evidence

Work only on the requested scope. Specification needs `power/PLAN.json`;
model validates its declared model files; simulation requires genuine native
ngspice results. Review additionally needs `power/REVIEW.md`.
This is circuit simulation, not construction, physical energizing or approval.

## Model and exact physics

Each project-relative model JSON has this shape:

```json
{
  "topology": "buck",
  "source": "Original illustrative constants, not a measured device",
  "validity": "Open-loop PWM and constant passive parameters",
  "limitations": ["No device charge, magnetic saturation or physical qualification"],
  "inductance_h": 0.0001,
  "capacitance_f": 0.000022,
  "inductor_resistance_ohm": 0.05,
  "capacitor_esr_ohm": 0.02,
  "switch_on_resistance_ohm": 0.02,
  "switch_off_resistance_ohm": 100000000,
  "diode_saturation_current_a": 1e-9,
  "diode_emission": 1,
  "diode_resistance_ohm": 0.02,
  "temperature_c": 27
}
```

`topology` is `buck` or `boost`. Buck has a high-side switch, low-side diode
and series output inductor. Boost has a series input inductor, low-side switch
and output diode. Both have the stated inductor resistance, capacitor ESR and
resistive output load. They start with zero inductor current and capacitor
voltage using native transient initial conditions, not a precharged DC state.

The switch is ngspice's voltage-controlled resistive switch, not a MOSFET model.
Its ideal control pulse has finite symmetric edges of one thousandth-period;
pulse plateau width compensates those edges so time above the 0.5 threshold
equals the declared duty fraction. There is no driver-power model.
The native diode has the declared Is, N and Rs, zero Cjo and Tt, and 27 degC
nominal model temperature. The study uses `temperature_c`; native diode
temperature dependence applies, but there is no electrothermal feedback.
L and C are linear. No arbitrary netlist, external model library or executable
SPICE control section is accepted. Unknown model/run fields are rejected.

Parameter suffixes specify units: H, F, ohm, A and degC. L is 1e-6..0.1 H;
C is 1e-7..0.01 F; series/on resistances are 1e-4..10 ohm; off resistance is
1e4..1e9 ohm; diode Is is 1e-15..1e-3 A and N is 0.8..3; temperature is
-40..125 degC. These are execution bounds, not realistic device-rating claims.

## Plan, observation windows and original limits

The original single-condition mode of `power/PLAN.json` has nonempty `objective`, a `requirements` ID-to-description
map, a nonempty distinct `limitations` string list, 1-8 declared `models`,
1-8 `runs`, and 1-32 `convergence` comparisons. IDs are a lowercase letter
followed by at most 31 lowercase letters, digits or underscores. Numeric
fields reject booleans and nonfinite values. Simulation reads only the model
files selected by runs; model scope inspects every declared model.

Each run has the following fields. The numerical bounds below are a particular
illustrative Buck example, not universal converter acceptance:

```json
{
  "id": "coarse",
  "model": "design/buck.json",
  "input_voltage_v": 12,
  "duty_cycle": 0.5,
  "frequency_hz": 50000,
  "load_resistance_ohm": 5,
  "duration_s": 0.004,
  "max_step_s": 2e-7,
  "windows": {
    "settled": {"kind": "steady", "interval_s": [0.003, 0.004]}
  },
  "checks": [{
    "id": "voltage",
    "requirement": "output",
    "window": "settled",
    "metric": "output_mean_v",
    "unit": "V",
    "minimum": 5.62,
    "maximum": 5.68
  }]
}
```

An optional `load_step` is an object containing `time_s`, `transition_s` and
`resistance_ohm`. Conductance ramps linearly from 1/initial-R to 1/final-R
over that interval and stays at the final value. This is a resistive-load
change, not a constant-current or constant-power load.

Input is 1..48 V, duty 0.1..0.8, frequency 1 kHz..500 kHz and load 0.1..10000
ohm. The ideal DC ratio is bounded to 48 V output and nominal load power to
100 W; startup peaks can exceed nominal values and must be measured.
Duration is 20..1000 periods and at most 1 s. Maximum time step is between
one thousandth and one fiftieth-period and passes a conservative 80000-point
estimate. Native waveform parsing permits at most 100000 points and 64 MiB.
The load change starts after ten periods, with transition length between
one thousandth and ten periods, and ends before the final five periods.

Declare 1-8 named windows and 1-32 checks per run. Every window needs a check;
every requirement needs a check. Each window spans at least two periods,
starts **after zero** and lies inside the native saved time range. With
transient initial conditions ngspice's first saved point is after t=0;
the checker does not invent an initial sample or extrapolate it.

Window kinds are `startup` (starts within the first tenth-period and precedes
any load change), `load_step` (contains the whole declared transition), and
`steady` (an integer number of at least ten periods, not crossing a load
change). In steady windows the first/last cycle means of output voltage and
inductor current must agree within 0.5 percent. Selecting a late-looking
interval does not by itself prove periodic steady behavior.

| Metric | Unit | Interpretation over the declared window |
|---|---|---|
| `output_mean_v`, `output_min_v`, `output_max_v`, `output_pp_v` | V | Time mean, minimum, maximum, peak-to-peak output voltage |
| `inductor_mean_a`, `inductor_min_a`, `inductor_max_a`, `inductor_pp_a`, `inductor_rms_a` | A | Time mean, signed extrema, peak-to-peak and RMS inductor current |
| `capacitor_rms_a` | A | RMS current through the modeled capacitor ESR |
| `switch_peak_v`, `switch_peak_a` | V, A | Absolute peak switch terminal voltage/current |
| `rectifier_reverse_peak_v` | V | Peak reverse diode terminal voltage |
| `input_power_w`, `output_power_w`, `loss_power_w`, `storage_rate_w` | W | Window-average source input, resistive load, modeled dissipation, change in stored L/C energy divided by duration |
| `energy_relative_error` | 1 | Absolute source/load/loss/storage energy residual divided by positive input energy |
| `cycle_mean_relative_change` | 1 | Worst relative change of output/inductor means between first and last cycle |

Native sampling is adaptive: arithmetic sample averages are wrong. The
checker integrates the product of piecewise-linear voltage/current signals,
including interpolated observation boundaries. RMS uses time-weighted squares.
Input power is `-V(in)*I(Vin)` under SPICE's passive source sign convention.
Loss includes winding/ESR dissipation and switch/diode terminal power.
Stored energy is `L*I(L)^2/2 + C*V(cap)^2/2`.

Every window, including startup and load transients, must satisfy
`Ein = Eload + Eloss + delta(Estored)` within 1e-3 relative error.
Do not require input/output power equality while L/C energy is changing.
These modeled losses omit real device switching charge, magnetic core loss,
driver consumption and other hardware losses; no measured efficiency is implied.
Checks carry independently chosen `minimum` and `maximum` bounds, never relaxed
after execution. Peak-to-peak values over startup are excursions, not steady ripple.

## Time-step comparison and native records

Every run participates in a declared coarse/fine comparison. Copy the physical
conditions and windows unchanged, use a distinct run ID, and reduce
`max_step_s` by at least half. Fine output must actually contain more native
samples. For the example above, add a `fine` run with `max_step_s: 1e-7` and:

```json
{"coarse": "coarse", "fine": "fine", "window": "settled",
 "metric": "output_mean_v", "max_delta": 0.01}
```

Compare other important ripple, peak and load-response metrics explicitly;
agreement of one metric does not establish accuracy of unexamined metrics.
Two step limits demonstrate only the declared agreement, not a proven error bound.

Install native ngspice >=42 and the declared numpy dependency. Initial validation
uses ngspice 42. The runner uses second-order Gear integration, fixed tolerances,
isolated startup configuration and actual `ngspice -n -b -r wave.raw -o
ngspice.log model.cir`. It monitors time/output size and stops runaway execution.
Failed attempts remain intact; `power/results` is never silently overwritten.

`power/results/RESULTS.json` contains `operation: "ngspice-converter"`, `status`,
`ngspice_version`, exact `inputs`/`outputs` independent-copy maps and ordered
`runs` with `id` and `execution` (`command`, absolute `cwd`, `log`, `exit_code`).
Each native run retains `model.cir`, ASCII `wave.raw`, `ngspice.log` and
`console.log`, with independent copies. The checker regenerates the circuit,
checks native completion, units, windows and original limits, and independently
re-executes ngspice in temporary directories. Every saved waveform variable and
sample must match replay; wall-clock headers and performance logs are not
numeric evidence. The project remains unchanged.

## Operating-envelope mode: fixed goal, full sampled coverage and margins

Alternatively, keep the plan's `objective`, `requirements`, `limitations`
and `models`, but replace `runs` and `convergence` with:

```json
{"robustness": {"specification": "design/operating.json", "design": {"duty": 0.5304}}}
```

Do not mix the two modes. The project-relative operating specification is a
separate original input, supplied or agreed before execution, outside results.
Do not rewrite it to make an unsuccessful task finish. Specification/model
scopes validate this complete declared study without running ngspice.
The following is an illustrative **design** specification, not universal limits:

```json
{
  "goal": "design",
  "source": "Original agreed finite operating study",
  "limitations": ["No full-interval or physical guarantee"],
  "model": "design/buck.json",
  "conditions": {
    "input_voltage_v": 12,
    "duty_cycle": 0.5304,
    "frequency_hz": 50000,
    "load_resistance_ohm": 5,
    "duration_s": 0.002,
    "windows": {"settled": {"kind": "steady", "interval_s": [0.0016, 0.002]}}
  },
  "design_variables": {
    "duty": {
      "target": "run.duty_cycle", "unit": "1",
      "source": "Allowed common fixed-duty decision",
      "minimum": 0.52, "maximum": 0.54
    }
  },
  "axes": [
    {"id": "supply", "target": "run.input_voltage_v", "unit": "V",
     "source": "Declared source samples", "values": [11.8, 12.2]},
    {"id": "capacitance", "target": "model.capacitance_f", "unit": "1",
     "source": "Declared capacitor tolerance", "factors": [0.8, 1.2]}
  ],
  "maximum_steps_s": [2e-7, 1e-7],
  "checks": [{
    "id": "voltage", "requirement": "regulation", "window": "settled",
    "metric": "output_mean_v", "unit": "V",
    "minimum": 5.8, "maximum": 6.2, "margin_lower": 0.02, "margin_upper": 0.02
  }],
  "convergence": [
    {"window": "settled", "metric": "output_mean_v", "max_delta": 0.005}
  ]
}
```

The plan must describe `regulation` in its requirements. `conditions` uses the
same physical fields and windows as a run, including optional `load_step`,
but has no per-run ID, model, checks or step size. All physical/model/window
bounds from the original mode still apply to every resolved sample.

The original specification fixes **one goal**:

| Goal | Design freedom | Task acceptance |
|---|---|---|
| `diagnose` | `design_variables: {}` and plan `design: {}`; use the supplied circuit/conditions unchanged | Complete valid evidence may conclude that limits or margins fail |
| `design` | Select exactly the declared variables, identically for every sample | All original checks and required margins must pass everywhere |

Neither goal accepts missing coverage, invalid energy/steady-window
measurements, failed native execution/replay, non-growing sample counts or
failed time-step comparisons. These mean the conclusion is not established,
not that a bad design has been successfully diagnosed.

Each design variable supplies a `target`, exact `unit`, nonempty `source` and
either 1-8 distinct allowed `values` or inclusive `minimum`/`maximum`.
No undeclared plan choices or duplicate targets are allowed. Targets are
`model.<numeric model field>` with its physical unit, or
`run.input_voltage_v` (V), `run.duty_cycle` (1), `run.frequency_hz` (Hz),
`run.load_resistance_ohm` / `run.load_step.resistance_ohm` (ohm).
A load-step target requires a declared actual step.

Declare 1-8 axes with distinct `id` and `target`, a `source`, and exactly one
of `values` (absolute physical values, correct physical unit) or `factors`
(positive multipliers, unit `1`, applied to the selected nominal quantity).
Each axis has 2-8 distinct finite values. Factors require a positive nominal
value and cannot multiply Celsius temperature; use absolute `degC` values.
An absolute axis cannot replace a selected design variable; a relative
component tolerance may multiply an allowed selected nominal component.

The runner evaluates the full Cartesian product, not one-at-a-time samples,
plus the nominal point. A grid point identical to nominal is counted once.
There are at most 17 scenarios including nominal; oversized requests fail
without dropping combinations. Every scenario gets coarse and fine native
runs, with fine maximum step at most half coarse and genuinely more samples.
Every checked `(window, metric)` requires an explicit refinement comparison.
The aggregate point estimate is at most 1,500,000.

Every check keeps the original bounds and optionally `margin_lower` and
`margin_upper` (nonnegative, default zero, same unit as the metric).
Lower headroom is `value - minimum`; upper headroom is `maximum - value`.
Requested margins must fit inside the original interval and be met at
both resolutions of every scenario. No rounding tolerance turns a negative
headroom into a pass. Worst **observed** headroom identifies its scenario and
run; it is not a proof of a global worst case.

`RESULTS.json` uses `operation: "ngspice-converter-corners"` and additionally
records `goal`, common `design`, all resolved `scenarios` and
`execution_complete`. Original plan/specification/model bytes and every
native input/output are retained as independent copies.
`power/results/ASSESSMENT.json` records engineering `status` (`passed`,
`failed`, or `incomplete`), `goal`, `conclusion_valid`, `task_accepted`,
expected/completed/measured coverage, per-run measurements, all check
headrooms, time-step comparisons and structured failures.

**A completed diagnosis can have `RESULTS.status: "complete"` and
`ASSESSMENT.status: "failed"` with `task_accepted: true`. This means the
diagnostic task finished and the circuit did not meet its requirements.**
The report must say so explicitly. `validate_simulation` / the stage checker
enforce task acceptance. `robustness.inspect_study(Path(...))` independently
replays and returns a completed positive or negative assessment without
requiring task acceptance. Saved assessments are not trusted without replay.

Limit/margin failures are collected after all runs, rather than stopping at
the first failed corner. Invalid measurements remain diagnostic entries but
prevent task acceptance. Native execution/schema/integrity/resource failures
stop with explicit errors and retained partial files; no fabricated numerical
result replaces them. Existing results are never overwritten.
Each execution or replay phase has a 600-second budget; original native
outputs total at most 512 MiB, with independent retained copies additional.
Each native call still has a 120-second/64-MiB maximum, further reduced by
the remaining execution budget. Replay uses temporary per-run outputs and
the same per-native limits.

Coverage is strictly a finite sample statement, not continuous-range
robustness, a yield/probability estimate or physical qualification. Component
factors are explicit model perturbations, not manufacturer distributions.
Temperature affects the native diode, but constant L/C and resistances gain
no undocumented temperature coefficients. No electrothermal feedback is added.

## Explicit exclusions

No closed-loop controller synthesis, arbitrary topology/CAD import, real
MOSFET/IGBT/SiC/GaN libraries, diode recovery, device capacitance, inductor
saturation/core loss, parasitic extraction, EMI certification, thermal
coupling, mains equipment, motor operation or physical energizing is executed.
Those remain important domain knowledge, not capabilities implied by this adapter.
