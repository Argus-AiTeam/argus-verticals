---
name: Digital Handshake and Elastic Pipelines
description: "Implement valid/ready transfer semantics, backpressure-stable payloads, elastic registers and bounded buffering without data loss or combinational loops."
---

# Handshake pipelines

## One transfer event

A transfer occurs on an active edge when `valid && ready`. The source must hold
valid and payload stable while stalled. It must not wait for ready before
asserting valid if the protocol allows a sink to wait for valid: that can deadlock.
Treat data, byte enables, packet boundaries, IDs and error bits as one payload.

Distinguish latency (cycles from acceptance to availability) from initiation
interval (cycles between accepted inputs). A pipelined operation can have high
latency and one-per-cycle throughput.

## Example: one-entry elastic register

```systemverilog
module dc_elastic8(
    input logic clk, rst,
    input logic in_valid,
    output logic in_ready,
    input logic [7:0] in_data,
    output logic out_valid,
    input logic out_ready,
    output logic [7:0] out_data
);
    assign in_ready = !out_valid || out_ready;
    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else if (in_ready) begin
            out_valid <= in_valid;
            if (in_valid) out_data <= in_data;
        end
    end
endmodule
```

The register supports simultaneous dequeue/enqueue and one item per cycle.
Reset discards a pending item. The payload is intentionally not reset and must
be ignored when invalid. The combinational ready path may become critical when
many stages are chained.

## Skid buffers and protocol boundaries

Registering ready delays backpressure by a cycle, so reserve storage for the
extra in-flight item. A skid buffer is not simply a registered ready bit.
Draw occupancy cases before coding. Avoid combinational loops across modules
whose valid depends on ready and whose ready depends on valid.

AXI-family channels have separate handshakes. AW and W may arrive independently;
assuming simultaneous address/data arrival loses legal writes. AXI-Stream TLAST
and TKEEP must stay aligned with data through stalls. Do not claim AXI compliance
from a generic ready/valid example.

## Verify

Keep a scoreboard keyed to accepted inputs and remove items only on accepted
outputs. Stall for zero, one and many cycles; alternate ready; sustain maximum
throughput; reset while full. Assert stalled output payload stability and
`outputs <= inputs` within each reset epoch. A progress proof needs bounded
stall assumptions or a fairness assumption on the sink.
