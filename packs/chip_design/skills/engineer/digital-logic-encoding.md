---
name: Digital Logic and Encoding
description: "Design complete combinational logic: truth tables, decoders, muxes, priority/one-hot encoding, X handling and hazard-aware interfaces."
---

# Logic and encoding

## Start with the function

Write input domains and a truth table or equivalent equations. Distinguish
mutually exclusive conditions from priority. A one-hot encoder is not a priority
encoder: multiple asserted inputs are illegal in the former, normal in the latter.
Choose explicit illegal-input behavior rather than treating it as don't-care
unless the environment guarantees and verifies that assumption.

For a mux, compare fan-in, logic depth and select distribution. Boolean minimum
literal count does not necessarily minimize mapped delay or routing. One-hot
selection trades more select wires for parallel qualification. Balanced trees
can reduce depth but may increase wires and switching.

## Example: lowest-index priority

```systemverilog
module dc_priority4(
    input logic [3:0] request,
    output logic valid,
    output logic [1:0] index
);
    always_comb begin
        valid = 1'b1;
        index = 2'd0;
        if      (request[0]) index = 2'd0;
        else if (request[1]) index = 2'd1;
        else if (request[2]) index = 2'd2;
        else if (request[3]) index = 2'd3;
        else                valid = 1'b0;
    end
endmodule
```

`index` is defined even when `valid=0`, but consumers must qualify it with valid.
This is combinational priority, not fair arbitration.

## Common failures

- Partial assignments infer storage. Give every output and temporary a default.
- `casex` can turn an unknown control into an apparently legal selection. Prefer
  explicit cases and separately assert control knownness in simulation.
- `unique case` expresses/checks assumptions; it does not repair an incomplete
  truth table or guarantee synthesis-equivalent unknown behavior.
- Combinational glitches are not removed by Boolean equivalence. Do not use a
  decoded pulse as a clock or asynchronous reset.

## Verify

Exhaust all 16 request patterns for this example, including zero and multi-hot.
Check `valid == |request`, and for a valid result that the selected bit is set
and no lower-index bit is set. Inject X/Z separately to expose control ambiguity;
two-state formal proofs cannot establish four-state simulator behavior. For a
larger mux/decoder, use a table-based oracle independent of the RTL expression.
