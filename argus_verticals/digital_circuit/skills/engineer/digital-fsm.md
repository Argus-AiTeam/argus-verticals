---
name: Digital FSM and Control Design
description: "Build explicit state-transition contracts, choose Moore/Mealy outputs and state encoding, and verify completion, recovery and liveness under stalls."
---

# FSM and control

## Derive states from obligations

A state represents what the circuit still owes its environment: idle, holding a
request, waiting for a response, draining, or reporting completion. Write a
transition table with input condition, next state, side effects and output cycle.
Separate architectural state from counters/flags; avoid redundant state variables
that can encode contradictory situations.

Moore outputs depend on current state; Mealy outputs also depend on inputs and
may create long combinational paths or glitches. Binary encoding uses fewer
flops; one-hot may simplify FPGA decode. Let synthesis choose unless a measured
constraint or safety requirement justifies explicit encoding.

## Example: one-cycle completion notification

```systemverilog
module dc_controller(
    input logic clk, rst, start, finished,
    output logic busy, done
);
    typedef enum logic [1:0] {IDLE, RUN, REPORT} state_t;
    state_t state, next_state;
    always_comb begin
        next_state = state;
        busy = 1'b0;
        done = 1'b0;
        case (state)
            IDLE: if (start) next_state = RUN;
            RUN: begin
                busy = 1'b1;
                if (finished) next_state = REPORT;
            end
            REPORT: begin done = 1'b1; next_state = IDLE; end
            default: next_state = IDLE;
        endcase
    end
    always_ff @(posedge clk)
        if (rst) state <= IDLE;
        else state <= next_state;
endmodule
```

`start` is accepted only in IDLE. REPORT does not accept another start, so this
example has a bubble; change the contract and tests if zero-bubble chaining is
required. A default transition is a defined simulation recovery behavior, not
proof that synthesis preserves fault-tolerant illegal-state recovery.

## Verify

Cover every legal transition, ignored starts while busy, finished arriving early,
reset in every state and consecutive transactions. Assert done is one cycle and
has a preceding accepted request. Prove liveness only under an explicit
environment assumption that `finished` eventually arrives; otherwise indefinite
RUN is correct waiting behavior. For a safety-critical recovery claim, examine
post-synthesis encoding and fault assumptions rather than trusting `default`.
