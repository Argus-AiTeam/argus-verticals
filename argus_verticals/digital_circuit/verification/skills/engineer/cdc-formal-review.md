---
name: CDC Reset and Nonvacuous Formal Review
description: "Inventory clock/reset crossings and formal assumptions; distinguish executable protocol properties from metastability, structural CDC and timing certification."
---

# Crossing analysis and proof limits

Build a crossing inventory: source/destination clocks, reset domains, signal
type, expected update rate, capture method and constraints. Single-bit levels
may use synchronizer chains; pulses need stretching, toggles or acknowledgment;
coherent multi-bit state needs a protocol, Gray encoding with implementation
constraints, or asynchronous storage. Independently synchronizing bus bits
does not preserve coherence. Synchronizer MTBF depends on real library/device
parameters and frequencies, not a two-flop drawing.

Reset-domain crossing is not just clock-domain crossing. Deassert asynchronously
asserted resets in each receiving clock domain; test reset order, partial-domain
reset, outstanding transactions and recovery. Independent resets on the ends
of an async FIFO require a defined flush/rejoin protocol. Formal models must
not assume away these permitted reset sequences.

Check synchronizer attributes, physical placement, reconvergence, combinational
logic before synchronizers, and fanout from the first synchronization stage
with an appropriate structural tool. Review every waiver with its exact path
and rationale. Gray-pointer CDC also needs skew/delay constraints; a logical
Gray transition alone does not bound physical arrival differences. A broad
false path is not evidence that a crossing is safe.

For formal work, classify environmental assumptions separately from DUT
assertions. Preserve the clock/reset model, initial-state assumptions, engines,
mode, depth and source harness. Never constrain DUT outputs to the desired
answer. Cover the antecedent of each important implication, accepted traffic,
full/empty boundaries and recovery. An unreachable antecedent can make a
property vacuously true; a timeout or unknown result is not a proof.

The `formal` profile requires successful native SymbiYosys results and cover
witnesses. Its checker verifies records, not whether assumptions are physically
valid. Simulation can expose reset/protocol bugs but cannot simulate
metastability or replace structural CDC/RDC analysis. Record uncovered
crossings explicitly and select external analysis work when needed; do not
report CDC closure from this specialty's simulation success.
