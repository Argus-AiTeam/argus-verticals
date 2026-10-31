---
name: Digital Verification and Formal Reasoning
description: "Build independent scoreboards and protocol properties, distinguish simulation/formal coverage, avoid vacuous proofs and preserve reproducible failure evidence."
---

# Verification and formal

## Verification plan

Map each requirement to a stimulus, observable check and evidence location.
Use transaction-level reference models where possible: model a FIFO as a queue,
an ALU as wider integer arithmetic, and a protocol as accepted events. Copying the
RTL's state transitions into the scoreboard can reproduce the same bug.

Layer combinational exhaustive checks, cycle-accurate directed tests, seeded
random tests, assertions and formal analysis. A regression that compiles but
never compares outputs is not a functional test.

## Example: executable arithmetic oracle

```systemverilog
module dc_sat_add8_tb;
    logic [7:0] a, b;
    wire [7:0] y;
    wire saturated;
    integer expected;
    dc_sat_add8 dut(a, b, y, saturated);
    initial begin
        for (integer x = 0; x < 256; x = x + 1)
            for (integer z = 0; z < 256; z = z + 1) begin
                a = x; b = z;
                expected = x + z;
                #1;
                if (y !== ((expected > 255) ? 8'd255 : expected[7:0]))
                    $fatal(1, "sum mismatch");
                if (saturated !== (expected > 255))
                    $fatal(1, "saturation flag mismatch");
            end
        $display("PASS: 65536 saturating-add cases");
        $finish;
    end
endmodule
```

The independent model uses wider integers and explicitly checks the flag.
Case inequality catches unknown output bits. Run with the arithmetic guide's
`dc_sat_add8` module and an explicit testbench top.

## Properties and assumptions

A ready/valid stability property is conceptually
`valid && !ready |=> valid && $stable(payload)`, disabled during the specified
reset interval. Safety says something bad never happens; liveness says something
good eventually happens. Bounded formal unrolling is not automatically an
unbounded proof. Record assumptions, reset model, bounds, engines and result.

Check vacuity: cover the antecedent, accepted traffic and meaningful terminal
states. An assumption such as `ready always high` makes stall properties easy
but removes precisely the behavior needing verification. Do not constrain DUT
outputs to force desired behavior.

## Reproducibility and triage

Freeze seeds and preserve the failing waveform/log before repair. Minimize the
stimulus while keeping the failure; classify specification, implementation,
testbench and environment errors separately. Never relax an oracle to make a
regression green without independently justified contract correction.
Report code/functional/assertion coverage separately, including excluded bins.
Passing tests are evidence within explored cases, not a claim of total correctness.
