---
name: Digital Clock Enable and Low Power
description: "Reduce switching with enables, operand isolation and appropriate clock gating; distinguish FPGA/ASIC implementation, power estimates, isolation and retention."
---

# Clock enable and low power

## Start with activity

Dynamic switching power is approximately `activity * capacitance * V**2 * f`.
Clock trees switch continuously unless deliberately gated. Leakage, short-circuit
power and physical implementation remain separate contributors. An RTL gate
count or toggle reduction alone is not a measured power result.

Clock enables preserve a single synchronous clock domain and usually map well to
FPGA register resources. ASIC integrated clock-gating cells may save clock-tree
power, but need enable timing, test bypass, generated-clock treatment and a
glitch-free implementation.

## Example: enabled state, not a gated clock

```systemverilog
module dc_enabled_register(
    input logic clk, rst, enable,
    input logic [7:0] data_in,
    output logic [7:0] data_out
);
    always_ff @(posedge clk)
        if (rst) data_out <= 8'd0;
        else if (enable) data_out <= data_in;
endmodule
```

Never replace this with `wire gated_clk = clk & enable` when enable can change
while clk is high. That can create a shortened or spurious clock pulse.
Use characterized clock-control resources and the target methodology.

## Other techniques

Operand isolation stops unused combinational cones from toggling but adds gates
and control paths. Resource sharing can reduce area while increasing muxing and
activity; compare workload-weighted energy, not just block area. Pipelining may
raise clock power even when it permits a lower voltage or higher throughput.

Power-domain shutdown needs ordered quiescence, isolation, state retention where
required, power-good/reset sequencing and a defined wakeup handshake. Describe
these in a power intent methodology such as UPF only when the chosen tools and
delivery scope support it; do not mistake RTL simulation for power-aware signoff.

## Verify

Prove enabled-state equivalence and state stability when disabled. Exercise
enable/reset priority and rapid enable toggling. For gated implementations, run
clock-gating checks and test-mode cases. Power comparisons need matched activity
windows, clock rates, voltage/corner and workload completion counts, with units
such as energy per transaction as well as average power.
