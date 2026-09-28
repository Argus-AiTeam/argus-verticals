---
name: Chip Interconnect and Subsystem Integration
description: "Design accelerator connectivity and integration contracts: buses/crossbars/NoCs, transaction ordering, arbitration, credits, deadlock and end-to-end completion."
---

# Interconnect and integration

## Build an endpoint contract table

For each endpoint, record clock/reset domain, address range, data width,
transaction size, ID width, ordering guarantees, outstanding limit and error
behavior. A width converter must preserve byte masks and address semantics; a
clock converter must preserve transactions, not merely synchronize each bit.

Identify completion responsibility. "Request accepted" means a queue owns work;
"operation complete" means all required effects and responses are visible.
Do not signal host completion while writes remain buffered unless the ABI
explicitly defines a weaker, safe ordering contract.

## Choose topology from traffic

A shared bus is inexpensive and simple but serializes contention. A crossbar
supports independent pairs at mux/wiring cost. A packet network scales physical
connectivity but adds buffering, routing, credits and verification work. Choose
from a traffic matrix and latency/throughput requirements, not a general claim
that a NoC is more advanced.

Use the inherited arbitration guide for local grants. At system level, specify
service class, burst ownership, starvation assumptions and which event advances
priority. A fair arbiter does not guarantee fairness when upstream queues block
head-of-line traffic.

## Ordering and deadlock

Track requests and responses by IDs and enforce the protocol's ordering domains.
If IDs are remapped, retain enough state to restore source identity. Build a
resource-dependency graph: request buffers, response buffers, credits, locks and
software waits can form cycles. Reserve a response path or use a justified
acyclic allocation policy where required.

## Integration and verification

Start with one producer and one consumer, then add contention, concurrency and
clock boundaries. Verify address decode exclusivity, inaccessible-address errors,
no response duplication, stable stalled payloads, ID reuse and reset flushing.
Add a system scoreboard that observes externally committed operations rather
than trusting only local unit tests.

Measure latency distribution and bandwidth under mixed traffic, not only one
uncontended stream. Preserve topology/configuration and queue assumptions in
the architecture document; support any deadlock-free claim with a proof or an
explicitly bounded verification statement.
