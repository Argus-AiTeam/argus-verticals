# RF and microwave network design

Independent `hardware / rf_design` domain, declared by
[`vertical.json`](vertical.json), with no digital or analog workflow parent.
Knowledge covers S parameters, matching, transmission lines, filters, active
RF behavior, noise, stability, measurement reference planes and physical limits.
The first executable backend is **scikit-rf network analysis**, not full-wave EM,
nonlinear RF simulation, fixture calibration or physical hardware certification.

## Select only the needed work

Profiles: `specification`, `model`, `analysis`, `review` (analysis plus review),
and optional `full` (all four stages). Custom combinations are supported; review
needs current analysis evidence but does not automatically rerun it. Analysis
can inspect one supplied Touchstone file or compose a small dependency graph of
ideal RLC/line models, explicit reference changes, port permutations and
two-port cascades. Unselected definitions are not calculated during analysis.

The [canonical evidence contract](evidence-contract.md) is supplied directly to
runtime roles, together with executable and read-only commands that work from
Store-only installations. It defines port order, power-wave conventions, units,
frequency limits, supported input formats and meaningful acceptance checks.
Generic file/number helpers come from `argus_verticals.hardware.shared`, bundled
by the manifest; they do not import another domain's workflow.
The host runs the selected checker and supplies its current result to the
read/search-only Reviewer under shared [review rules](../hardware/shared/hardware-review.md).
It does not replace independent examination of the physical assumptions, run
arbitrary recorded project commands or turn an accepted diagnosis into a
passing design.

## Local execution

Install the declared dependencies in the interpreter used by Argus:

```bash
pip install -e ".[rf]"
python -m argus_verticals.rf_design.run_reference /tmp/new-rf-reference
python -m argus_verticals.rf_design.run_robustness_reference /tmp/new-rf-tolerance-reference
python -m argus_verticals.rf_design.run_analysis /path/to/project
```

Separate child processes in Store-only installations must load the provider
through Argus, as the role commands do, or include the store in `PYTHONPATH`.
Results are Touchstone 2.0 RI files with explicit per-port reference impedances.
Inputs and outputs have independent byte-current copies; results never
overwrite an existing study. The checker recomputes exported networks and
measurements rather than trusting a JSON success flag.
For real-reference renormalization, a direct wave-basis linear solve is used
on the scikit-rf network instead of an intermediate Z matrix. Ideal thru and
series-element Z matrices can be singular; avoiding that conversion preserves
their reference-change accuracy without hidden eigenvalue regularization.

## Finite component and frequency robustness

The optional `robustness` plan selects an original external specification and
one common set of design choices. The specification owns the ideal network
graph, component provenance/validity, positive relative tolerance factors,
original limits, headroom and frequency-refinement tolerances.
The runner evaluates the **full Cartesian product plus nominal**, never a
convenient subset or separately retuned corners. It recalculates every ideal
network on the original frequency grid and a grid with every midpoint added.
No measured Touchstone data is interpolated to manufacture a finer experiment.

Retained case models and Touchstone exports are independently recomputed.
`rf/results/ASSESSMENT.json` reports complete coverage, sampled full-matrix
passivity and reciprocity, worst observed frequencies/corners, original-limit
headroom and coarse/fine deltas. `goal: "diagnose"` can accept an explicitly
failed engineering conclusion; `goal: "design"` must pass all original limits
and required margins. Missing cases, invalid measurements and failed numerical
refinement cannot complete either goal.

The reference checks an ideal 50-to-100 ohm L-match across independently varied
L/C +/-5 percent samples over 0.8-1.2 GHz, with a five-point original grid and
nine-point fine grid. The four combinations plus nominal produce ten real
network calculations. These are finite samples, not guaranteed continuous-band
performance, a global tolerance bound, statistical yield or physical qualification.

The 0.2.1 follow-up fixes exact-decimal headroom boundaries without relaxing
limits, and limits dB zero checks to the selected frequencies and their
interpolation support. Full-grid phase unwrapping remains unchanged. Existing
assessments are not rewritten to the new arithmetic; retain them and run a
fresh study when upgrading.

## Independent executable references

Six studies use original, explicitly synthetic models:

- Matched 0.5-amplitude attenuator: S21 = 0.5, or -6.0206 dB.
- Its cascade with itself: S21 = 0.25, or -12.0412 dB.
- Series 50 ohm resistor with 50 ohm references: S11 = 1/3, S21 = 2/3.
- The same resistor renormalized to 75 ohms: S11 = 1/4, S21 = 3/4.
- Matched quarter-wave line at 1 GHz: S21 = -j.
- Lossless 50-to-100 ohm L-match at 1 GHz: series L = 50/(2*pi*f),
  followed by shunt C = 1/(2*pi*f*100); zero reflection and unit transmission
  magnitude with the **50/100 ohm port references**, phase -45 degrees.

Positive-real-reference passivity uses the full S matrix's largest singular
value, not merely its individual port power sums. Reciprocity is checked under
the same stated normalization. Samples cannot establish global passivity,
causality, stability, manufacturability or calibration quality.

## Authoritative references

- [scikit-rf network tutorial](https://scikit-rf.readthedocs.io/en/latest/tutorials/Networks.html)
- [Renormalization and wave definitions](https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.network.Network.renormalize.html)
- [Touchstone reader](https://scikit-rf.readthedocs.io/en/latest/api/io/generated/skrf.io.touchstone.Touchstone.html)
- [Touchstone specification](https://ibis.org/touchstone_ver2.0/touchstone_ver2_0.pdf)

No vendor model, proprietary measurement dataset or copyrighted reference
corpus is bundled.
