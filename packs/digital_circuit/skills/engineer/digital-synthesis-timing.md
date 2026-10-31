---
name: Digital Synthesis and Timing
description: "Connect synthesizable RTL to inference and timing evidence: clock/I/O constraints, setup/hold, critical-path diagnosis, pipelining and target-specific reports."
---

# Synthesis and timing

## Define the implementation question

Specify target FPGA or library/corner, clock waveform, input/output delays,
uncertainty and generated clocks. `Fmax = 1 / delay` is meaningful only when the
reported delay includes the intended timing path and constraints. An unconstrained
endpoint can make a summary look clean without establishing any requirement.

For a simple same-clock path, setup requires data arrival before the next capture
edge minus setup/uncertainty; hold requires data not arrive too soon after the
current edge. Setup and hold fixes differ. Reducing logic delay can improve setup
while worsening hold. Clock skew and clock uncertainty must not be conflated.

## Example: pipeline with explicit two-edge latency

```systemverilog
module dc_pipeline8(
    input logic clk,
    input logic [7:0] data_in,
    output logic [7:0] data_out
);
    logic [7:0] first;
    always_ff @(posedge clk) begin
        first <= data_in;
        data_out <= first;
    end
endmodule
```

The output takes two sampling edges to reflect a new input. Without valid/reset
control, initial values are unspecified. In a real protocol, pipeline payload
and validity together; inserting this block is a functional interface change.

## Diagnose before optimizing

Read the actual startpoint, endpoint, path group and cell/net delay split.
Long mux/adder chains suggest restructuring or pipelining; dominant wire delay
suggests placement/fanout/locality. High-fanout enables may need buffering or
partitioning. Inspect RAM/DSP inference, latch reports and inferred arithmetic
widths before replacing operators with hand-coded structures.

An SDC starting point might use `create_clock -period 10 [get_ports clk]`, but
that alone leaves I/O timing unspecified. Do not blindly copy false-path or
multicycle exceptions. A multicycle setup change normally needs a corresponding
hold relationship and a verified functional enable condition.

## Evidence and acceptance

Preserve exact commands, source/configuration identity, tool version, constraints,
raw timing and utilization reports, warnings and unconstrained-path counts.
Compare candidates under the same target/corner/constraints/memory assumptions.
Synthesis estimates are not post-route area/timing/power. If tools are unavailable,
say so; an out-of-scope synthesis stage is omitted, not a fabricated passing run.
