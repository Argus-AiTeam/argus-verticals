---
name: Digital CDC and Reset Domain Crossings
description: "Select synchronizers for levels, pulses and buses; reason about metastability, async FIFO pointers, reconvergence, reset release and physical constraints."
---

# CDC and RDC

## Classify the crossing

List source/destination clocks, frequency relationship, data type, change rate,
coherency requirement and reset relationship. A two-flop synchronizer is suitable
for a slowly changing single-bit level whose intermediate values may be missed.
It is not a general pulse catcher, bus synchronizer or metastability eliminator.

Metastability failure probability decreases with resolution time; MTBF also
depends on clock/data rates and characterized cell parameters. Never report an
MTBF value without technology-specific inputs and physical timing assumptions.

## Example: level synchronizer

```systemverilog
module dc_sync_level(
    input logic dst_clk, dst_rst,
    input logic async_level,
    output logic synced_level
);
    (* ASYNC_REG = "TRUE" *) logic meta, stable;
    always_ff @(posedge dst_clk) begin
        if (dst_rst) begin meta <= 1'b0; stable <= 1'b0; end
        else begin meta <= async_level; stable <= meta; end
    end
    assign synced_level = stable;
endmodule
```

`dst_rst` here is already synchronous to `dst_clk`. Register the source when
possible to reduce glitches. Do not fan out the first stage into other logic.
Attributes must be supported by the chosen synthesis/implementation tools.

## Choose the right protocol

- Pulse: toggle encoding plus destination edge detection, with a minimum spacing
  guarantee, or request/acknowledge so events cannot overrun the receiver.
- Stable multi-bit payload: bundled-data handshake; hold the bus unchanged until
  acknowledgement and prove capture ordering.
- Continuous stream: asynchronous FIFO, normally Gray-coded pointers and
  destination-domain pointer synchronization. Gray code assumes one source
  increment at a time; it still needs physical skew/max-delay constraints.
- Related controls: do not synchronize independently and then assume they remain
  mutually consistent. Analyze reconvergence and encoded transitions.

Reset deassertion must be synchronized separately for each clock domain, with
minimum assertion duration and stopped-clock behavior specified. Different reset
epochs can invalidate FIFO pointers, toggles or outstanding handshakes. Plan
quiescence/flush/recovery; a synchronizer does not solve reset protocol alignment.

## Verify and constrain

Use structural CDC/RDC analysis, assertions and variable clock ratios/phases.
Test reset of either side during traffic and event spacing boundaries.
RTL simulation cannot model analog metastability or prove silicon MTBF.
Review synchronizer placement, path constraints and reconvergence waivers.
Do not hide all cross-domain paths with blanket false paths without checking
the data-coherency and skew obligations that remain.
