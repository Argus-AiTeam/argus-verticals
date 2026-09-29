# RF evidence requirements

Choose only the requested network studies. All paths are nonempty project-local
files, not absolute paths or paths containing `..`. All JSON numbers are finite
SI values. No implicit frequency resampling, port reinterpretation, impedance
renormalization or clipping is permitted.

## One plan and explicit network conventions

`rf/PLAN.json` contains `objective`, a nonempty `requirements` map of IDs to
observable descriptions, and nonempty `limitations`. The specification scope
needs only these fields. Model work adds `networks`; analysis also needs `studies`.
Preparing these records inside analysis does not require separate earlier stages.

This minimal analysis inspects an existing two-port:

```json
{
  "objective": "Check the supplied passive two-port in its stated reference planes",
  "requirements": {"transmission": "S21 magnitude agrees with the supplied independent expectation"},
  "limitations": ["Only the sampled small-signal network is assessed, not physical certification"],
  "networks": {
    "device": {
      "kind": "touchstone",
      "path": "data/device.s2p",
      "ports": ["input", "output"],
      "source": "State whether this is measured, simulated or an analytic model, and its actual origin",
      "validity": "State the frequency, bias, reference-plane and operating conditions",
      "limitations": ["State missing calibration, model or physical information"]
    }
  },
  "studies": [{
    "id": "transmission",
    "network": "device",
    "checks": [{
      "id": "s21",
      "requirement": "transmission",
      "metric": "s_magnitude",
      "ports": [2, 1],
      "statistic": "at",
      "at_hz": 1000000000,
      "unit": "1",
      "minimum": 0.49,
      "maximum": 0.51
    }]
  }]
}
```

The example bounds are not universal RF requirements. Establish the real
acceptance conditions from the request and independent equations/reference data
before execution. Every numerical requirement needs a check. IDs start with a
lowercase letter and contain at most 48 lowercase letters, digits or underscores;
study IDs and each study's check IDs are distinct.

`networks` is a named dependency graph, not a mandatory sequence. Analysis builds
only the selected studies and their dependencies. Model-only work validates all
declared models. Cycles and unknown dependencies are errors.

Leaf networks (`touchstone`, `lumped`, `line`) require `source`, `validity` and
nonempty `limitations`. Derived networks record their explicit dependencies:

- `touchstone`: `path` and distinct `ports` labels in physical file order.
  Accept UTF-8/ASCII `.s1p` through `.s8p`, or `.ts`, with an explicit option line
  such as `# GHz S RI R 50`. Touchstone 1.0, 2.0 and 2.1 S data are supported in
  RI, MA or DB form. Reference impedances must be positive, real, constant over
  frequency, and may differ by port. Noise blocks and mixed-mode definitions are
  rejected rather than silently ignored. Serialized Python Network files are
  not accepted.
- `lumped`: explicit increasing `frequency_hz` samples, `z0_ohm: [left, right]`,
  and ordered `elements`. Each element has `kind: R|L|C`,
  `connection: series|shunt` and positive `value_si` in ohms, henries or farads.
  These are ideal elements. Port 1 is on the left, port 2 on the right.
- `line`: the same frequency and two-port references, positive
  `impedance_ohm`, nonnegative `delay_s` and `loss_db`. This is a uniform line
  with total propagation `loss_db*ln(10)/20 + j*2*pi*f*delay_s`, not an extracted
  geometry, dispersive material or full-wave model.
- `renormalize`: `input` network ID and `z0_ohm`, one positive real reference per
  port. This changes wave references, not the physical circuit or calibration.
  A direct real-wave basis solve avoids the singular impedance-matrix
  conversion of an ideal thru or series element; no eigenvalue clipping is used.
- `reorder`: `input` and a complete one-based `ports` permutation. `[2,1]`
  reverses a two-port's external labeling; it does not take a network inverse.
- `cascade`: ordered `inputs` IDs, left to right, joining port 2 to port 1.
  Each operand must be a two-port on exactly the same frequency samples, with
  equal reference impedances at the junction. Use an explicit renormalize node
  first when needed. No hidden interpolation or mismatch insertion is performed.

Power-wave conventions are explicit. With positive real references these agree
with the usual traveling-wave normalization. Complex/frequency-dependent
references, mixed-mode conversion, fixture calibration/de-embedding, noise
parameters, nonlinear behavior and electromagnetic field solving are outside
this first adapter. Limits: 64 definitions/studies, 10001 frequency points,
8 ports, 32 MiB per input, and 64 elements or cascade operands. Frequencies
are strictly positive; this is not a DC circuit solver.

## Numerical acceptance

Checks declare `metric`, `statistic`, `unit`, inclusive finite `minimum` and
`maximum`. S metrics also need `ports: [response, incident]`, **one-based**:
S21 is `[2,1]`, even though a library array uses zero-based indices.

- `s_real`, `s_imag`, `s_magnitude`: dimensionless, unit `1`.
- `s_db`: `20*log10(abs(Sij))`, unit `dB`. Transmission attenuation is negative
  S21 dB; positive return loss is the negative of S11 dB.
- `s_phase_deg`: continuously unwrapped phase, initially on the principal
  branch, unit `deg`. Ensure frequency sampling does not alias phase rotations.
- `sigma_max`: largest singular value of the full S matrix, unit `1`.
  Passivity at a sample requires this to be no larger than one within a
  justified tolerance. Individual column-power tests are insufficient.
- `reciprocity_error`: maximum `abs(Sij-Sji)` at a sample, unit `1`, under the
  supported real-reference, single-ended conventions.

Statistics are `at` with `at_hz`, or `min`/`max` with `window_hz: [start, stop]`.
Measurements use saved data and linear interpolation of the chosen scalar
metric in frequency. They never extrapolate. Extrema and passivity comparisons
cover the sampled network, not unsampled resonances or global causality.
An exactly zero S parameter has no finite dB/phase value: use magnitude bounds
for exact ideal matches or isolation, not an arbitrary logarithmic floor.

## Actual calculation and retained results

Use the supplied runner, not a hand-written success summary. It refuses existing
`rf/results`, copies the plan and the dependency closure's source files to
`rf/results/inputs`, calculates from that copied project, and writes Touchstone
2.0 RI results with explicit per-port references to `rf/results/networks/<id>.ts`.
Independent retained copies are under `rf/results/retained/`.

`rf/results/RESULTS.json` records the Python/numpy/scikit-rf versions, the actual
library `operation`, execution `status`, exact `inputs` mappings, `studies`
(id/network/path), and exact `outputs` mappings. This is an in-process library
calculation, not a fabricated external simulator command. Failed calculations
retain their error and any available partial results.

The read-only checker verifies current independent file copies, exact requested
study IDs, reloaded export grids/references/S matrices against recomputation,
and every numerical acceptance bound. Serialization comparisons use rtol 1e-11
and atol 1e-12 for S only; they do not relax engineering acceptance bounds.
Native success text and supplied measurement summaries are not authority.

Preserve old results before an intentional rerun. Never merely refresh copies
around old outputs. The review scope additionally needs `rf/REVIEW.md` stating
requirements met/missed and limitations. Every scope requires independent
review. Record consistency does not prove authentic measurements, model
adequacy, calibration quality, global stability or physical safety.
