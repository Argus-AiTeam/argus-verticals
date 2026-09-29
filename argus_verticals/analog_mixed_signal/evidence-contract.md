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
