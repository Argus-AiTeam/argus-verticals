---
name: Chip Memory Hierarchy and DMA
description: "Model accelerator storage and traffic, choose banks/ports/buffering, define DMA address/burst contracts and verify ownership, ordering and bandwidth."
---

# Memory hierarchy and DMA

## Count capacity and traffic separately

Capacity asks what must be resident simultaneously. Traffic asks what crosses a
boundary per output, tile or inference. Write byte counts with precision, padding,
metadata, alignment and reuse assumptions. An on-chip capacity fit does not imply
sufficient ports or external bandwidth.

Arithmetic intensity is useful operations per transferred byte at a named
boundary. A roofline bound is `min(peak_compute, bandwidth * intensity)` in
consistent units. Include achieved rather than advertised bandwidth when claiming
measurements; an architectural study should label assumed efficiency explicitly.

## Banks, ports and buffers

Derive simultaneous reads/writes from the schedule. Bank mapping must avoid
conflicts for supported strides; modulo banking can behave poorly for adversarial
strides. Replication increases read ports but complicates writes and capacity.
Double buffering overlaps transfer and compute only when ownership swaps are
atomic and both capacities/bandwidths suffice.

For each buffer, specify producer/consumer, size, layout, ready/valid or credits,
initial owner and release event. Prevent overwriting data still in use. Account
for returned-but-not-consumed responses when sizing outstanding queues.

## DMA contract

Define address width, element size, strides, alignment, burst limit, boundary
splits, masks, IDs, outstanding count and ordering. Separate issued, accepted
and completed requests. A last-beat indication is not completion until accepted.
Address arithmetic needs a wide enough intermediate and explicit overflow checks.

AXI4 bursts must not cross a 4 KiB boundary. For a transfer near a boundary,
split at the minimum of bytes remaining, legal burst length and boundary
distance, then account for beat alignment and strobes. Use the actual protocol
specification for unaligned rules rather than assuming every bus behaves alike.

## Verify and measure

Use a byte-addressable memory oracle and a separate queue of outstanding
transactions. Test page boundaries, unaligned/partial tails, zero/one/max lengths,
backpressure on every channel, reordered responses where legal, errors and reset
mid-transfer. Poison guard regions to detect unintended writes.

Report effective payload bandwidth, protocol overhead, bank-conflict stalls,
queue occupancy and compute starvation. Preserve the memory model and traces;
do not call a data-free DMA stub a validated memory subsystem.
