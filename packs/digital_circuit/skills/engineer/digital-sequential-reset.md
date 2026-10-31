---
name: Digital Sequential Circuits and Reset
description: "Specify clocked state, enables, reset assertion/release, latency and counter behavior; separate architectural state from uninitialized datapath storage."
---

# Sequential circuits and reset

## State contract

Define the active clock edge, reset polarity, synchronous/asynchronous assertion,
release requirements and priority relative to enable/load. Nonblocking
assignments model simultaneous register updates: every RHS reads pre-edge state.
The testbench should sample after updates, not race the DUT at the same edge.

Reset architectural control/valid state. Resetting every data bit can prevent
RAM/DSP inference and create a large reset network. Unreset data is safe only
when valid control prevents it from becoming architecturally observable.

## Example: enabled modulo counter

```systemverilog
module dc_counter8(
    input logic clk, rst, enable,
    output logic [7:0] count
);
    always_ff @(posedge clk) begin
        if (rst) count <= 8'd0;
        else if (enable) count <= count + 8'd1;
    end
endmodule
```

Reset is synchronous and dominates enable. Overflow wraps modulo 256. Holding
enable low preserves state; adding `else count <= count` is unnecessary.

## Alternatives and pitfalls

Synchronous reset is timed as data/control and requires an active clock.
Asynchronous assertion can reset a stopped domain, but release must satisfy
recovery/removal; use a domain-specific synchronized deassertion strategy.
Do not assume a simulator's zero initialization matches silicon power-up.

Loadable counters need explicit load-versus-count priority. Terminal detection
using the old count versus next count changes the output cycle. A timer that
loads N and pulses at zero may take N+1 cycles depending on its contract.
Do not generate a divided clock by logic and use it as an ordinary data enable;
clock trees and generated-clock constraints need deliberate treatment.

## Verify

Exercise reset while enable is both high and low, consecutive reset cycles,
hold sequences, wraparound, and restart after reset. Count transfers rather than
wall-clock cycles when enable means acceptance. For asynchronous reset designs,
vary assertion phase in simulation and review release topology and timing
separately; simulation cannot certify metastability reliability.
