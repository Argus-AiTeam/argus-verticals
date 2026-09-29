---
name: FPGA Engineering Map
description: "Choose FPGA-specific resource, constraint, implementation and bring-up guidance without importing ASIC certification assumptions."
---

# FPGA engineering map

Use digital-circuit skills for behavior and verification; this domain owns
device resources, target constraints, implementation and board observations.
Separate portable RTL from board wrappers and generated/vendor IP.

| Concern | Decisions and evidence |
| --- | --- |
| Target | Exact part/package/speed grade, tool version, oscillator, board revision |
| Resources | LUT/FF mapping, carry chains, DSP packing, BRAM read/write mode and port conflicts |
| Clock/reset | Dedicated clock resources, PLL limits, generated-clock relationships, lock/reset sequencing |
| I/O | Pin and bank assignment, voltage, I/O standard, differential pair/termination, external timing |
| Implementation | Synthesis/placement/routing results, real constraints, warnings, frequency and resource margin |
| Board behavior | Programming permission, device identity, clock observation, reset, traffic, error recovery |
| Host integration | Stable CSR/DMA protocol, drivers, buffering, reproducible host/FPGA versions |

Read [resource and timing design](fpga-resources-timing.md) before committing to
an architecture and [board bring-up](fpga-board-bringup.md) before touching a
device. The first executable adapter is single-clock iCE40; knowledge of a
different family is not a claim that its implementation has been validated.
Use the minimum supported scope. A request to implement RTL does not authorize
programming hardware or require a physical device.
