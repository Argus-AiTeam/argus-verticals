---
name: Ngspice Analysis and Native Evidence
description: "Execute selected analyses from copied inputs, use native waveforms as numerical authority, and preserve failed runs rather than fabricating success records."
---

# Prepare only the requested study

Read the always-present evidence contract for exact fields and commands.
Prepare `analog/PLAN.json` from the supplied circuit requirements and independent
equations. Do not infer acceptance bounds from the result you are about to judge.
For a simulation-only request, preparing this manifest is normal setup; it does
not authorize unrelated specification, layout or board work.

In legacy mode, give each requested condition a stable descriptive ID and a deck
containing one `.op`, `.dc`, `.ac` or `.tran` command. Operating-envelope mode
instead expands the original parameter specification automatically. Name every
included file and its provenance. Project-relative
`.include` paths make the copied execution tree self-contained. Avoid `.control`
scripts, external model loading or multiple native plots in a single run.
Use `.save` to retain the signals and denominators actually needed for checks.

Use the supplied `run_analysis` function rather than manually inventing its
result structure. It runs ngspice, captures commands and native output, preserves
input/output copies and recomputes bounded measurements. The checker rejects
changed files, missing plots, nonfinite data, wrong analysis types, inadequate
axis ranges and ambiguous crossings. Failed bounds block legacy/design
completion but remain valid findings for a fixed envelope diagnosis. A normal exit or printed
PASS is not numerical evidence by itself.

Choose adequate frequency/time resolution for interpolation and the physical
event of interest. Current extrema checks are not general settling, FFT or RMS
analysis. When changing a circuit, excitation, model or acceptance condition,
preserve the previous results before an intentional rerun. Never merely refresh
the copies around old waveforms. Explain numerical problems and unsupported
methods explicitly; independent review still checks the scientific meaning.

In operating-envelope mode, keep every out-of-limit observation in the
assessment. A fixed `diagnose` goal may finish with a valid negative conclusion;
a `design` goal may not. Neither can finish with missing cases, invalid
measurements or failed refinements. Use the canonical stage command so an
unchanged accepted numerical comparison is reused while report wording is
corrected.

Copy combined worst-case values from the assessment with their explicit
resolution and parameter coordinates. Label fine-only displays separately.
Distinguish raw bound headroom from the signed surplus after the required
margin; preserve coarse-only failures even when a fine-run display looks better.
