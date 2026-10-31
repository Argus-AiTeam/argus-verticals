---
name: Digital Arbitration and Interconnect
description: "Choose priority/round-robin arbitration, ownership duration, buffering, credits and ordering; reason about starvation and resource deadlock."
---

# Arbitration and interconnect

## Separate eligibility, grant and acceptance

A request may be present but ineligible because a destination is blocked or no
credit remains. A grant proposes ownership; accepted transfer commits it.
Round-robin priority should advance on the contract's service event, not merely
because a requester raised a bit.

Fixed priority is small and deterministic but can starve lower priorities.
Round-robin bounds wait in *successful service opportunities*, not clock cycles
under arbitrary downstream stalls. Weighted arbitration expresses bandwidth
shares but needs a definition for unused quotas and changing eligibility.

## Example: two-requester round robin

```systemverilog
module dc_rr2(
    input logic clk, rst,
    input logic [1:0] request,
    input logic accept,
    output logic [1:0] grant
);
    logic prefer_one;
    always_comb begin
        case (request)
            2'b01: grant = 2'b01;
            2'b10: grant = 2'b10;
            2'b11: grant = prefer_one ? 2'b10 : 2'b01;
            default: grant = 2'b00;
        endcase
    end
    always_ff @(posedge clk)
        if (rst) prefer_one <= 1'b0;
        else if (accept && |grant) prefer_one <= grant[0];
endmodule
```

This is a per-service arbiter, not a stalled valid/ready output implementation.
If a grant drives a transaction that must remain stable while blocked, latch the
selected owner/payload until acceptance. Burst locking additionally needs an
end-of-burst or abort rule.

## Scaling decisions

Crossbars cost roughly input-count times output-count mux connectivity; buses
share bandwidth, and packet networks add buffering/routing complexity. Credits
count actual free slots, including in-flight traffic. Analyze the resource
dependency graph: round-robin fairness alone cannot remove a cycle of buffers
waiting on each other.

## Verify

Assert one-hot-or-zero grants and `grant & ~request == 0`. With both requests
persistent and acceptance asserted, check alternating service. Hold acceptance
low and ensure no priority advance; test one requester dropping out. For a
transactional interconnect, separately verify stable ownership, response IDs,
ordering, timeout/error behavior and credit conservation.
