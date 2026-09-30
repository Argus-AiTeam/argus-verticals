---
name: Analog Scope Selection
description: "Choose analog circuit work independently from RTL, RF, board layout and physical qualification, without forcing every simulation method."
---

# Route the requested physical question

Use this domain for analog circuit requirements, bias, model assessment,
small-signal response, feedback, filters and appropriate circuit simulation.
An existing RC or amplifier analysis is a simulation scope, not a request to
design a chip or produce a paper. Distinguish a request to explain a device
model from a request to execute it.

Choose specification, model, simulation or the explicit review/full option
according to the desired result. The simulation plan can select only AC,
only transient, only operating point or a small justified combination.
Even full studies use only the needed methods. An omitted analysis must remain
an omitted claim, not a fabricated success entry.

Digital logic/testbench execution belongs to digital verification; FPGA build
and board configuration belong to FPGA design. RF/EM analysis, PCB layout,
packaging and power-stage hardware work are not automatically included because
they contain analog components. If the necessary domain or adapter is not yet
available, state that limitation instead of quietly broadening this one.

Preserve the operator's circuit, filenames, numerical targets and non-goals.
Model or analysis setup can supply missing record structure, but not missing
physical assumptions by guesswork. Ask about ambiguity that changes the result.
The native checker validates records and stated numerical comparisons; it
cannot authorize hardware operation, establish a PDK entitlement, or replace
independent review of model adequacy and experimental meaning.

An existing circuit with a supplied operating specification is still a scoped
analog simulation/review task. Preserve its diagnosis/design distinction.
A valid diagnosis can report noncompliance; a design conclusion requires all
original sampled limits and margins. Missing coverage or unreliable numerical
measurements cannot justify either completion.
