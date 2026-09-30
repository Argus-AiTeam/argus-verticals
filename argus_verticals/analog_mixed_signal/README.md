# Analog and mixed-signal circuits

Independent domain `hardware / analog_mixed_signal`. It has no digital-circuit
skill or workflow parent. It covers analog requirements, component/device models,
bias and small-signal reasoning, amplifiers, feedback, filters, noise, variation,
data converters and analog/digital interfaces through topic skills.
The [`vertical.json`](vertical.json) manifest declares this independent provider
and its bundled shared helpers.

**Executable support is narrower than the knowledge map:** ngspice operating
point, single-variable DC sweep, AC and transient analysis of project-local
circuits. This is not a foundry PDK integration, physical design/DRC/LVS flow,
RF/EM solver, noise/PSS adapter, or mixed-language co-simulation system.
Circuit equations and behavioral models are not evidence of manufactured
device performance. No hardware is energized or programmed.

## Flexible scopes

| Profile | Selected stages | Result |
| --- | --- | --- |
| `specification` | specification | Observable requirements and explicit limits |
| `model` | model | Circuit/model files with provenance and validity |
| `simulation` | simulation | Only the requested native analysis kinds and measurements |
| `review` | simulation, review | Current numerical evidence and a qualified conclusion |
| `full` | specification, model, simulation, review | Complete documented study of the requested circuit |

Custom stage combinations are supported. Review includes simulation evidence;
it need not rerun an unchanged, valid result. Every execution scope still needs
its plan and model descriptions, which can be prepared within that scope.
`full` does **not** force every analysis kind: the plan selects only the methods
needed by the requirements. Missing tools or failed bounds are explicit failures.

## Local use

Install ngspice separately (for example `apt install ngspice` on Debian/Ubuntu).
The Python implementation uses only the standard library. The native reference
is exercised with ngspice 42; CI installs and runs the distribution's ngspice.
Argus must expose composable scopes and `VerticalPlugin.routing_path`.

From an environment where this package is importable:

```bash
python -m argus_verticals.analog_mixed_signal.run_reference /tmp/new-analog-reference
python -m argus_verticals.analog_mixed_signal.run_robustness_reference /tmp/new-analog-envelope
python -m argus_verticals.analog_mixed_signal.run_robustness_reference /tmp/new-analog-diagnosis --goal diagnose --tight
python -m argus_verticals.analog_mixed_signal.run_analysis /path/to/project
```

For Store-only installations, prepend the store for separate Python processes:

```bash
STORE_ROOT="$(python -c 'from argus.verticals.store import store_root; print(store_root())')"
PYTHONPATH="$STORE_ROOT${PYTHONPATH:+:$PYTHONPATH}" python -m argus_verticals.analog_mixed_signal.run_analysis /path/to/project
```

The role prompts include the **same canonical [evidence contract](evidence-contract.md)**
and separate execution/read-only commands using Argus's own interpreter and
provider loader.
The checker does not depend on optional skill retrieval. Shared file/copy/number
checks are bundled from `argus_verticals.hardware.shared`; they do not import
digital verification rules or select a parent workflow.
The native reader and scalar measurements now live in
`argus_verticals.hardware.spice.raw`, shared with the independent power domain.
Existing `analog_mixed_signal.raw` imports remain compatible; analysis behavior
and the analog workflow are unchanged.

## Executable references and limits

Version 0.2 adds an optional externally supplied operating specification. It
binds named global parameters, original nominal values and model-validity ranges
to one common allowed design and the full Cartesian sample set plus nominal.
Only the analyses needed by the question are selected; the original plan format
is unchanged.

Every sample is evaluated at coarse/fine settings. DC halves its step, AC doubles
its density (or linear intervals), and transient halves its explicit maximum
step and output interval; those methods must actually produce more saved points.
All methods also use a separately declared tighter relative tolerance. OP has no
sweep grid: its comparison is solver-tolerance sensitivity, not grid convergence.
Each metric needs an original absolute comparison tolerance. This is evidence
of the specified sensitivity, not a mathematical error bound or a general
settling/stability guarantee.

The original `goal` separates task completion from circuit compliance.
`diagnose` can accept a complete, numerically valid negative conclusion;
`design` must satisfy every sampled original bound and required margin.
Missing measurements, ambiguous crossings and failed refinements block both.
`analog/results/ASSESSMENT.json` contains all violations, worst measured
headroom, full coverage and separate `conclusion_valid`/`task_accepted` fields.

Version 0.2.1 makes the worst-case resolution explicit and records signed
surplus after required margins, so a fine-only table cannot silently stand in
for the combined coarse/fine result. Decimal suffixes and relative factors are
converted without an extra binary rounding step; exact model bounds remain
strict. Include inspection reuses parsed files but counts every expanded byte,
rejecting undeclared sources before reading and decks expanding beyond 4 MiB.
Native regressions also cover an underdamped second-order RLC network:
resonant gain and transient overshoot match independent equations, while a
window containing multiple rising crossings is rejected as an invalid
single-crossing measurement rather than accepted as a negative diagnosis.

Version 0.2.2 also names the installed provider and actual Argus task runtime
root in role context. The native CLI's scratch directory is not a replacement
for that runtime state; overriding it creates a separate validation history.
Decimal products retain all operand digits, including integer factors, before
binary conversion so strict model bounds do not depend on intermediate rounding.

New studies retain the exact generated circuit for each sample and resolution.
Independent validation recreates it from original inputs and replays every
waveform. Subsequent checks compare byte copies in external Argus runtime state;
unchanged numerical evidence is reused across report-only changes. Source/tool
changes invalidate reuse, and changed code in a running checker requires restart.
This uses trusted host state, not a sandbox against processes allowed to edit it.

The new reference exercises a loaded RC network and an explicitly modeled diode
at 17 conditions with all four analysis kinds. Independent expectations include
`H0=Rload/(R+Rload)`, `tau=(R || Rload)*C`, the resulting transfer/step responses,
and Shockley forward voltage with declared Is/N/EG/XTI/TNOM. Temperature changes
the native diode, not an invented passive temperature coefficient. Wide original
bounds pass; the separately requested tight gain specification passes nominal
but fails some corners.

The bounded subset permits at most 17 scenarios, four analyses, 32 checks per
analysis, 32 source files, 4 MiB of original input and 1,500,000 estimated points.
Each native call is limited to 120 seconds and 64 MiB; each execution/replay
phase has 600 seconds and 512 MiB of original output, with retained copies extra.
Noise/PSS, Monte Carlo yield, arbitrary dynamic model loading and foundry claims
remain outside the executable scope.

The legacy `run_reference` creates a new directory and performs six genuine analyses:
RC operating point, DC transfer, AC response and step response, plus operating
point and AC response of a finite-gain, one-pole feedback amplifier.

The independent expectations are `fc = 1/(2*pi*R*C)`, `tau = R*C`,
`Acl = A0/(1+A0*beta)` and `fcl = fp*(1+A0*beta)`. For the RC reference,
R=1 kohm and C=100 nF; for the amplifier, A0=100000, fp=10 Hz, beta=1/11.
Bounds account for dense-sweep interpolation, not post-hoc fitting.

The amplifier is a deliberately simple linear behavioral model. It has no
supply rails, saturation, slew rate, current limit, noise, mismatch or extracted
parasitics. Its closed-loop bandwidth is not a measured loop stability margin
or a claim about a commercial op-amp. Real models require documented source,
license/access, operating ranges and relevant independent comparisons.

The runner preserves failed native output and refuses to overwrite a prior
result. Native waveforms, not a JSON success flag, determine numerical acceptance.
This checks record consistency and the stated equations; independent review
still evaluates the circuit, model, excitation and adequacy of the comparison.

## References

- [Official ngspice documentation](https://ngspice.sourceforge.io/docs.html):
  batch invocation, netlist syntax, analyses, raw output and numerical options.
- [Ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-html-manual/manual.xhtml):
  device equations, dependent sources, AC linearization and transient analysis.
- The executable examples are original, hand-written ideal/behavioral circuits;
  no proprietary PDK, vendor model or copyrighted reference corpus is bundled.
