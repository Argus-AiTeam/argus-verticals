# Analog evidence requirements

Work only on the requested scope and methods. All metadata file paths are
project-relative, remain inside the execution project, and may not contain `..`.
Numbers in JSON are finite SI values, not strings such as `"100n"` or `"1k"`.
SPICE files retain normal SPICE syntax: `m` means milli and `meg` means mega.

## One plan, progressively completed

`analog/PLAN.json` begins with:

```json
{
  "objective": "Check the supplied RC response without changing its topology",
  "requirements": {"bandwidth": "The cutoff agrees with the independently calculated RC value"},
  "limitations": ["Ideal passive model; no parasitic, noise or physical-board claim"],
  "models": {
    "bench.cir": {
      "kind": "ideal",
      "source": "Supplied circuit and its documented component values",
      "validity": "Linear passive model over the declared frequency range",
      "limitations": ["No measured component model or extracted layout"]
    }
  },
  "runs": [
    {
      "id": "rc_ac",
      "kind": "ac",
      "netlist": "bench.cir",
      "checks": [
        {
          "id": "cutoff",
          "requirement": "bandwidth",
          "vector": "v(out)",
          "denominator": "v(in)",
          "component": "magnitude",
          "statistic": "crossing",
          "window": [100, 10000],
          "level": 0.7071067811865476,
          "direction": "falling",
          "unit": "Hz",
          "minimum": 1585,
          "maximum": 1598
        }
      ]
    }
  ]
}
```

The example bounds are illustrative, not universal RC requirements. Derive
bounds from the actual request, equations, component/model tolerances and
declared numerical accuracy **before** inspecting the simulation result.

`specification` requires objective, nonempty requirement descriptions and
limitations only. `model` additionally requires actual files and their
`models` entries (`ideal`, `behavioral`, `device` or `testbench`, with source,
validity and limitations). `simulation` requires all these fields and nonempty
`runs`. Its setup may create a missing plan from the supplied requirements;
that does not add the separate specification/model stages or authorize changing
the circuit. Reuse an applicable existing plan rather than silently replacing it.

Run/check/requirement IDs use lowercase letters, digits and underscores and
begin with a letter, at most 48 characters. Run IDs and each run's check IDs
are distinct. Every check names a declared requirement; all declared numerical
requirements must be covered. Record non-numerical exclusions in limitations.

## Supported native analyses

Choose `op`, `dc`, `ac` or `tran` per run. Each deck has a title on its first line
and exactly one matching analysis directive. `.include`/`.inc` use literal
**project-root-relative** paths. All decks and included files need model
metadata; their complete include closure is copied before execution.

The first adapter does not support `.control`, `.lib`, external HDL/OSDI loading,
file-driven stimuli/models, nested DC sweeps, noise/PZ/TF/distortion/PSS analyses,
or multi-plot raw files. Do not substitute a simulation result from one method
for an unsupported one. AC's internal operating-point calculation is normal;
do not add a separate `.op` output to an AC deck. Use `.save` for required vectors.

The supplied runner uses ngspice batch mode with `-n` (ignore local/user
spiceinit), `-r`, `-o`, and `SPICE_ASCIIRAWFILE=1`. It records the installed tool
version. It runs from `analog/results/inputs`, using a copy of the original
project layout, and writes native files under `analog/results/runs/<id>/`.
The fixed command's `../runs/` arguments are internal paths relative to that
copied working directory; they are not metadata paths or permission to read
outside the project. Each subprocess has a 120-second limit; partial output
and unsuccessful execution records remain available on failure.

## Measurements are recomputed from native waveforms

Every check declares `vector`, `component`, `statistic`, `unit`, `minimum` and
`maximum`. Bounds are inclusive. Optional `denominator` forms a signal ratio;
zero denominators are errors, not zero gain.

Components are `real`, `imag`, `magnitude`, and continuously unwrapped
`phase_deg` (initial phase uses the principal branch). Phase is undefined at
zero amplitude; sampling must be dense enough not to alias phase rotations.
Voltage/current units are `V`/`A`; equal-dimension ratios use `1`, impedance
uses `ohm`, admittance `S`, and phase `deg`.

Statistics:

- `point`: the single operating-point value; only for `op`.
- `at`: interpolate at numeric `at`, in the native axis's SI units.
- `min` / `max`: extrema in an explicit `window: [start, stop]`.
- `crossing`: exactly one crossing of numeric `level` within `window`, with
  `direction: rising` or `falling`. Level is in the selected signal component's
  units; the measured result is the axis coordinate (`Hz`, `s`, `V` or `A`).
  A plateau, no crossing or multiple crossings is not a unique result.
  Touching a threshold and returning to the same side does not count as crossing.

Interpolation is linear in the saved axis, not a fitted transfer function.
Declare a sufficiently dense sweep/timestep and tolerances that account for
interpolation and solver error. Measurements never extrapolate beyond saved
data. Descending single-variable DC sweeps are supported; other axes must be
strictly increasing. The reader accepts at most 128 vectors, 100000 points and
64 MiB per raw file. Native AC frequency uses only its real coordinate:
ngspice 42 can leave the unused imaginary scale slot unspecified.

## Executed results, not hand-written success summaries

Use the supplied runner instead of inventing result JSON. It writes
`analog/results/RESULTS.json` with `tool_version`, `environment`, `inputs`,
`runs`, and `outputs`. `inputs` maps the plan and every model/deck to its
corresponding independent file copy under `analog/results/inputs/`.
Each run records its exact `id`, actual argv `command`, `cwd`, integer zero
`exit_code`, `raw`, native `log`, and captured `console` output.

`outputs` maps each waveform/log/console file to an independent retained copy.
Changed source, model, plan or output bytes invalidate old results. Self-copies
and hardlinks are invalid. The reader checks native plot kind, vector types,
point counts, finite signals, monotonic axis and the native log's row count,
then recalculates every measurement and compares it with the declared bounds.
Supplied summary numbers or PASS text are never numerical authority.

The runner refuses an existing `analog/results` directory. Inspect existing
evidence first. For an intentional rerun after a repair, preserve the old
directory separately before running again; do not merely refresh copies to
make stale measurements look current.

The `review` stage additionally requires `analog/REVIEW.md`, describing
requirements met/missed, model assumptions, convergence/numerical limitations
and excluded physical claims. Independent review is required in every selected
scope, not only in this report stage. Consistent files do not prove authentic
execution, adequate models, sufficient numerical resolution or physical safety.

## Parameter operating-envelope mode

Keep the original plan's `objective`, `requirements`, `limitations` and `models`,
but replace `runs` with:

```json
{"robustness": {"specification": "design/operating.json", "design": {}}}
```

The specification is a separate original input, outside results, with `goal`,
`source`, `limitations`, `parameter_file`, `parameters`, `design_variables`,
`axes`, `relative_tolerances` and `analyses`. Do not change that original goal or
its limits to make an unsuccessful study finish.

`goal: diagnose` holds the supplied design fixed and requires empty design
variables/choices. Complete valid numerical evidence may honestly conclude that
some sampled conditions fail. `goal: design` requires every original sampled
limit and margin; its plan chooses exactly the allowed common variables.
Missing data, ambiguous measurements or failed numerical comparisons cannot
complete either goal.

Each top-level deck must include the declared parameter file. It contains one
literal `.param name=value` per line, plus optional blank/comment lines; names
are lowercase identifiers. Decimal/exponent values and the native `t`, `g`,
`meg`, `k`, `m`, `u`, `n`, `p`, `f` suffixes are supported. No expressions or
multiple assignments occur in that file. Do not redeclare/shadow these sampled
parameters elsewhere. The Reviewer must still establish that the circuit
actually uses them and that their physical meanings and ranges are justified.
Suffixes are combined with the decimal exponent before binary conversion
(`100n` equals `1e-7`). Relative samples multiply the canonical decimal values
before one binary conversion. This avoids representation-only boundary failures;
model limits are still strict, not widened by an acceptance epsilon.

For an existing deck using parameters `r` and `c`, an illustrative specification
is:

```json
{
  "goal": "diagnose",
  "source": "Original agreed finite RC study",
  "limitations": ["Ideal passives; finite samples, not hardware approval"],
  "parameter_file": "design/parameters.inc",
  "parameters": {
    "r": {"nominal": 1000, "minimum": 500, "maximum": 2000,
          "unit": "ohm", "source": "Original resistor model"},
    "c": {"nominal": 1e-7, "minimum": 5e-8, "maximum": 2e-7,
          "unit": "F", "source": "Original capacitor model"}
  },
  "design_variables": {},
  "axes": [
    {"id": "r", "parameter": "r", "unit": "1", "factors": [0.9, 1.1],
     "source": "Agreed resistor tolerance samples"},
    {"id": "c", "parameter": "c", "unit": "1", "factors": [0.9, 1.1],
     "source": "Agreed capacitor tolerance samples"}
  ],
  "relative_tolerances": [0.0001, 0.000001],
  "analyses": [{
    "id": "response", "kind": "ac", "netlist": "bench.cir",
    "checks": [{
      "id": "gain", "requirement": "bandwidth", "vector": "v(out)",
      "denominator": "v(in)", "component": "magnitude", "statistic": "at",
      "at": 1000, "unit": "1", "minimum": 0.7, "maximum": 0.95,
      "margin_lower": 0.01, "margin_upper": 0.01, "max_delta": 0.001
    }]
  }]
}
```

Every original literal parameter is described exactly once; its nominal value
must match the file. Units are `V`, `A`, `ohm`, `F`, `H`, `Hz`, `s`, `1` or `degC`.
Declared minimum/maximum values are the model's valid range, not device ratings;
all samples and choices must stay inside it. A design variable maps its name to
`parameter`, `minimum`, `maximum`, `source`; the plan supplies its one value.
Axes use either distinct absolute `values` in the parameter unit, or positive
dimensionless `factors` around the common selected nominal. Factors cannot apply
to Celsius temperatures or nonpositive nominal quantities. An absolute axis
must not overwrite a common design choice.

Use the complete Cartesian product plus nominal. An identical nominal grid
point is counted once, not simulated twice. No automatic thinning, one-at-a-time
replacement or statistical-yield interpretation is allowed. A `.temp {temp_c}`
statement can vary native model temperature through a declared parameter;
this does not invent temperature coefficients for other components.

Choose 1-4 analyses and 1-32 checks per analysis. Each has its own original
top-level, single-analysis deck and the same measurement fields as above, plus
mandatory absolute `max_delta` in the measured unit. Optional
`margin_lower`/`margin_upper` default to zero and fit inside the original bounds.
Every requirement has a check. Unknown operating-specification fields are errors.

The runner creates both resolutions without changing original files:

- OP keeps `.op`; it compares the two declared relative tolerances only.
- DC supports one V/I source, literal start/stop/step and an integer number of
  intervals, including descending sweeps. The fine step is half the original.
- AC supports `lin`, `dec`, `oct`; fine doubles intervals or samples per log unit.
- Transient requires `.tran tstep tstop tstart tmax [uic]` with all four literal
  numbers. Fine halves tstep and tmax, preserving duration, start and initial
  condition semantics.

Both resolutions also apply the supplied relative tolerances: coarse at most
1e-2, fine at least 1e-12 and at most coarse/10. Remove conflicting source
`reltol` options explicitly; other supplied solver settings remain unchanged.
Non-OP refinement must actually increase saved sample count. Every check must
meet its original comparison tolerance at every scenario. These comparisons do
not prove a global error bound, a full settling guarantee or loop stability.

The bounded subset allows 17 scenarios, 32 source files, 4 MiB of original input,
4 MiB of expanded source per deck and 1,500,000 estimated native points.
Undeclared includes are rejected before their contents are read. Repeated files
are inspected once, but their repeated bytes and analysis commands still count
in the expansion; cyclic includes remain errors. Native calls are bounded to 120 seconds
and 64 MiB; each execution/replay phase has 600 seconds and 512 MiB of output
including generated decks, excluding independent retained copies.
Native diagnostics require investigation rather than a successful diagnosis.

`analog/results/RESULTS.json` records `ngspice-analog-corners`, the fixed goal,
tool version, exact cases, actual commands, original inputs and independent
native-output copies. Every case retains its generated `inputs/`, `wave.raw`,
`ngspice.log` and `console.log`. `ASSESSMENT.json` records all violations,
worst observed upper/lower headroom with actual parameters, coverage and every
refinement, separating engineering `status` from `conclusion_valid` and
`task_accepted`.

Each check's `resolution_scope` is `["coarse", "fine"]`: its
`worst_observed_lower`/`worst_observed_upper` cover both resolutions, not just
the preferred fine run. Each observation names its `resolution`.
`lower_headroom=value-minimum` and `upper_headroom=maximum-value` describe
distance to the bounds. The corresponding `*_margin_surplus` additionally
subtracts the required margin; a positive headroom can therefore still fail.
Use those exact worst observations, including run, resolution and parameters,
in the report. A fine-only table is allowed when labeled, but cannot replace
the combined worst-case summary or omit coarse-only failures.

The read-only checker regenerates every case from original source and
independently replays all native waveform samples before accepting new evidence.
Successful comparison can be retained in external Argus runtime state.
Unchanged numeric inputs/results and checker/tool identity are compared by
independent byte copies, not timestamps or a project-local passed flag.
Report-only edits still require independent review, but no new native replay.
Without trusted external state, the checker always replays. Do not write runtime
validation records as project work.
