---
name: Chip Verification Architecture
description: "Connect unit, subsystem and end-to-end verification with independent models, source-bound evidence, coverage and profile-aware acceptance."
---

# Verification architecture

## Three levels of confidence

Unit checks establish local arithmetic/control/protocol behavior. Subsystem
checks establish interactions such as compute consuming DMA data under stalls.
End-to-end checks establish host-visible numerical results, ordering and
completion. Passing all units does not prove integration.

Choose independent models at each level: wider integer arithmetic, byte memory,
transaction queues and a workload interpreter. Differential testing against a
software implementation is useful only if data formats, layout, saturation and
quality tolerances match the hardware contract.

## Verification plan

Map requirements to tests/properties and coverage bins. Cross relevant dimensions:
shape class, precision, reset state, backpressure pattern, error type and clock
ratio. Avoid claiming the full cross-product was covered when only a few seeds
ran. Distinguish code coverage, functional coverage and property proof status.

Check conservation invariants: accepted commands equal completed plus outstanding
plus explicitly aborted commands; read/write responses match issued operations;
output elements match the declared shape. Include reset epoch in scoreboards so
stale responses cannot be counted as new work.

## Repairs and reuse

Keep the first failing seed, log and waveform, minimize the failure, then repair
the owning contract or implementation. Re-run directly affected tests and the
integration path. Do not change tolerances or disable assertions merely to
accept new output.

Reuse accepted evidence only when source, configuration, constraints and relevant
assumptions still match. The existing evidence validators bind reports to current
sources; do not bypass them because the selected profile omits architecture or
RTL creation. An inherited report from another revision is not current evidence.

## Profile-aware result

`verification` and `rtl` profiles can finish on real verification evidence without
producing PPA/prototype/sign-off files. State the tested configurations and limits
in the result. A `full` physical delivery additionally requires the later gates;
functional correctness cannot stand in for timing, physical or foundry checks.

Preserve commands, exit codes, model/source provenance, seeds, raw artifacts and
coverage explanations in the existing verification schema. A summary-only pass,
self-referential oracle or absent raw output must fail acceptance.

The host provides the current completion check to the read/search-only Reviewer.
Do not impersonate Reviewer execution or solve missing authority with another
Engineer-only checking task. For numerical work, bind the original precision
contract, oracle dependencies and retained inputs using the existing project
records; the general verification specialty supports explicit `supporting_files`.

Historical campaigns keep their own runtime, native task and experiment rules.
Validate a repaired command entry and fresh-process import order with synthetic,
no-claim fixtures before requesting a new scientific owner. Do not run a closed
prefix, acquire a claim, replay a rejected attempt or relabel an unmeasured
entry failure merely to produce a passing verification record.
