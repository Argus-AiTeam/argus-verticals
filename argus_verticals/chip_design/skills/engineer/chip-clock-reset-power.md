---
name: Chip Clock Reset and Power Architecture
description: "Organize clock/reset/power domains, reset epochs, quiescence and wakeup sequences; connect CDC/RDC requirements to constraints and target-level evidence."
---

# Clock, reset and power architecture

## Domain inventory

Create one table for clocks, resets and power domains. Include source, nominal
and allowed frequency, generated-clock relationship, reset polarity, assertion/
release policy, stopped-clock behavior and crossing endpoints. Assign an owner
to each clock/reset assumption so integration does not leave it implicit.

Use the inherited CDC/RDC guide for crossing primitives. A single-bit synchronizer
does not make a command bus coherent, and an async FIFO does not define recovery
when only one side resets. Treat reset as an epoch change for outstanding work.

## Reset and quiescence

Define boot sequence, reset order, initialization completion, and when interfaces
may assert ready. A domain entering reset must either finish outstanding work,
reject it deterministically or participate in a documented flush protocol.
Specify software-visible effects: lost commands, errors, interrupt clearing and
when retries are safe.

Example power-down sequence: stop accepting commands, drain/abort outstanding
transactions, acknowledge quiescence, assert isolation, save retained state if
required, stop clocks and switch power. Wakeup reverses only the steps justified
by the actual technology and power-good/reset requirements; blindly reversing a
list is not a verified sequence.

## Implementation constraints

Clock gates, PLLs, reset synchronizers and isolation/retention cells are
technology-specific resources. Do not substitute generic combinational logic.
Record timing exceptions, CDC max-delay/skew constraints and test-mode behavior.
For FPGA use dedicated clock resources and target-supported reset/inference
patterns; for ASIC use the selected library and power-intent flow.

## Verification and claims

Exercise independent reset phases, stopped clocks, restart under traffic and
power-state transitions at legal/illegal boundaries. Check no phantom completion,
no stale response crossing epochs and no X leakage through valid outputs.
Keep structural CDC/RDC, STA and power-aware simulation results separate.

Architecture/RTL profiles can document these obligations without claiming
physical closure. Full physical delivery needs the chosen target's actual
clock-tree, recovery/removal, isolation and relevant sign-off evidence.
