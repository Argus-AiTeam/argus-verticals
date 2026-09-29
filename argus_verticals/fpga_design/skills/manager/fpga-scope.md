---
name: FPGA Scope and Tool Boundary
description: "Choose RTL, implementation or physical bring-up independently; never program hardware just because a build succeeded."
---

# Select the FPGA result

Use this domain for FPGA-specific targets, constraints and board execution.
Generic circuit fundamentals remain `digital_circuit`; chip architecture and
ASIC implementation remain `chip_design`. Only the single-clock iCE40 adapter
currently has executable implementation acceptance. Clarify unsupported device
families or timing requirements rather than claim a generic successful build.

Use `rtl` without adding a bitstream or board task. `implementation` creates a
bitstream but does not program a device. `bringup` and `full` need actual
measurements and explicit operator permission before programming. Missing tools
or hardware are reported as missing prerequisites, not N/A successes.
