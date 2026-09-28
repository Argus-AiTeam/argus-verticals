---
name: Digital Parameters and Elaboration
description: "Make reusable RTL legal across parameter corners: clog2, zero-width vectors, signed constants, address wrap, generate branches and configuration verification."
---

# Parameters and elaboration

## Treat configurations as interfaces

List legal ranges and relationships, not just defaults. Width, depth, lane count,
latency and protocol options can change both elaborated structure and semantics.
Test the minimum, a non-power-of-two case, representative normal values and the
largest supported configuration. A successful default build is not parameter
coverage.

`$clog2(1)` is zero. Pointer widths often need a minimum of one bit, while
occupancy widths use `$clog2(DEPTH+1)`. Signed unsized constants and shifts can
truncate or sign-extend unexpectedly; type/size operands deliberately.

## Example: depth-bounded pointer

```systemverilog
module dc_pointer #(
    parameter integer DEPTH = 3,
    parameter integer AW = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
    input logic clk, rst, step,
    output logic [AW-1:0] ptr
);
    initial begin
        if (DEPTH < 1 || AW < ((DEPTH > 1) ? $clog2(DEPTH) : 1))
            $fatal(1, "illegal pointer parameters");
    end
    always_ff @(posedge clk)
        if (rst) ptr <= '0;
        else if (step) begin
            if (ptr == DEPTH-1) ptr <= '0;
            else ptr <= ptr + 1'b1;
        end
endmodule
```

The explicit terminal comparison supports non-power-of-two depth. `initial`
parameter checks are simulation/elaboration diagnostics; confirm tool support
or enforce equivalent checks in the generator/build flow for synthesis.

## Avoid structural traps

Use generate branches when depth-one or zero-optional-lane behavior changes
legal indexing. Do not leave an illegal part-select in an elaborated branch and
hope runtime conditions hide it. Derive address widths separately from data
widths. Prevent users from overriding a derived width inconsistently, or validate
that relationship.

## Verify

For DEPTH=1, the pointer always remains zero. For DEPTH=3, cover 0->1->2->0 and
assert `ptr < DEPTH`; for DEPTH=8, check ordinary wrapping. Exercise reset and
held step in every configuration. Negative tests should fail visibly on illegal
parameters, not instantiate a plausible but incorrect circuit.
