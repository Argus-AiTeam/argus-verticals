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

Give each requested condition a stable descriptive ID and a deck containing
one `.op`, `.dc`, `.ac` or `.tran` command. Separate conditions when a larger
matrix is justified. Name every included file and its provenance. Project-relative
`.include` paths make the copied execution tree self-contained. Avoid `.control`
scripts, external model loading or multiple native plots in a single run.
Use `.save` to retain the signals and denominators actually needed for checks.

Use the supplied `run_analysis` function rather than manually inventing its
result structure. It runs ngspice, captures commands and native output, preserves
input/output copies and recomputes bounded measurements. The checker rejects
changed files, missing plots, nonfinite data, wrong analysis types, inadequate
axis ranges, ambiguous crossings and failed bounds. A normal exit or printed
PASS is not numerical evidence by itself.

Choose adequate frequency/time resolution for interpolation and the physical
event of interest. Current extrema checks are not general settling, FFT or RMS
analysis. When changing a circuit, excitation, model or acceptance condition,
preserve the previous results before an intentional rerun. Never merely refresh
the copies around old waveforms. Explain numerical problems and unsupported
methods explicitly; independent review still checks the scientific meaning.
