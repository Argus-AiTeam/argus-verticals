---
name: Digital Memories and FIFOs
description: "Specify RAM latency/ports/collisions and synchronous FIFO occupancy, pointer wrap, simultaneous operations, reset and backpressure invariants."
---

# Memories and FIFOs

## Memory contract before inference

Specify capacity, data width, port count, clock domains, read latency, write mask
granularity and read-during-write behavior. Read-first, write-first and no-change
are distinct. A behavioral array does not guarantee a target RAM macro or its
collision semantics. Confirm inference reports when synthesis is in scope.

A flop array allows flexible ports at high area cost. SRAM/BRAM is denser but
constrains ports, latency and reset. Banking increases parallelism only when
addresses avoid bank conflicts. Replication buys read ports at storage cost.

## Example: depth-four synchronous FIFO

```systemverilog
module dc_fifo4(
    input logic clk, rst,
    input logic in_valid,
    output logic in_ready,
    input logic [7:0] in_data,
    output logic out_valid,
    input logic out_ready,
    output logic [7:0] out_data
);
    logic [7:0] mem [0:3];
    logic [1:0] rd, wr;
    logic [2:0] count;
    wire push = in_valid && in_ready;
    wire pop = out_valid && out_ready;
    assign in_ready = count < 3'd4;
    assign out_valid = count != 0;
    assign out_data = mem[rd];
    always_ff @(posedge clk) begin
        if (rst) begin rd <= 0; wr <= 0; count <= 0; end
        else begin
            if (push) begin mem[wr] <= in_data; wr <= wr + 2'd1; end
            if (pop) rd <= rd + 2'd1;
            case ({push, pop})
                2'b10: count <= count + 3'd1;
                2'b01: count <= count - 3'd1;
                default: ;
            endcase
        end
    end
endmodule
```

This small example uses asynchronous array read and is not a synchronous-read
BRAM template. It does not accept a push while full, even if a pop happens that
cycle. There is no empty bypass. Both choices reduce control complexity but may
add bubbles. Data while `out_valid=0` is unspecified; valid state, not the array,
is reset. Reset flushes all queued items.

## Generalize carefully

For arbitrary depth, explicitly wrap at DEPTH-1; binary pointer overflow works
only for power-of-two depths. Count needs `ceil(log2(DEPTH+1))` bits, with legal
DEPTH>=1. A pointer-plus-phase full/empty scheme needs separately derived
invariants. Do not transfer binary pointers directly between asynchronous clocks.

## Verify

Use an independent software queue updated only on accepted transfers. Check
ordering, no duplication/loss, count bounds, empty/full attempts, simultaneous
push/pop, repeated wrap and reset while nonempty. Sweep depth 1, 2, 3 and a
larger power of two for parameterized versions. For inferred RAM, test and review
same-address collisions and the actual target read latency.
