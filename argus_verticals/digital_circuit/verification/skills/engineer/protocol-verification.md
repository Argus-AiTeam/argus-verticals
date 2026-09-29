---
name: Protocol and CSR Verification
description: "Verify AXI/APB/streaming/CSR/DMA behavior with independent channel scoreboards, register side effects, error responses and reset epochs."
---

# Protocol checks beyond arithmetic

For ready/valid traffic, transfer occurs only when both signals are sampled
asserted at the defined edge. Check payload stability while valid is held
without ready. Separate safety (no loss, duplication, corruption) from liveness;
a consumer allowed to stall forever makes unconditional eventual completion
unprovable. State fairness or maximum-stall assumptions rather than assuming
ready is always high.

AXI address, data and response channels progress independently. Test write data
arriving before the address, delayed responses, independent stalls, multiple
outstanding IDs and permitted reordering. A scoreboard needs per-ID queues and
burst/beat counters, not one global outstanding flag. Check byte enables,
alignment, burst address progression, last-beat timing, response codes and the
4-KiB boundary restriction. Do not apply full-AXI burst semantics to AXI-Lite or
silently require full AXI when a peripheral needs only APB.

APB setup and access phases differ: select/address/control are stable through
wait states; enable rises for access; errors are sampled only on completing
access. Check back-to-back transfers and reset during a wait. Avoid issuing a
new setup immediately after a non-completing access.

For CSRs, freeze address, reset value, width and access type. Model W1C, W1S,
read-clear, self-clearing command bits and reserved bits independently. Cross
byte strobes with partial writes and hardware-updated status. A simultaneous
event and W1C write needs an explicit priority rule; otherwise software can
lose interrupts. Verify interrupt masking, pending state, acknowledgment and
deassertion latency separately.

For DMA, track descriptor acceptance, reads/writes, short transfers, alignment,
outstanding limits, error propagation and completion ordering. Conserved work
equals completed plus outstanding plus explicitly aborted work. Include a reset
epoch so stale responses are not attributed to a new command. Use injected bus
errors, not only random payloads. Keep the host register-to-DMA-to-result-to-
interrupt path as a distinct integration test; passing IP unit tests does not
prove the assembled subsystem.
