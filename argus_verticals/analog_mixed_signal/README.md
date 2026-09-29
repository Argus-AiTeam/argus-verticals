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

## Executable references and limits

The reference creates a new directory and performs six genuine analyses:
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
