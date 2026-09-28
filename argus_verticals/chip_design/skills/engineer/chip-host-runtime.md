---
name: Chip Host Compiler and Runtime Contract
description: "Define the hardware/software boundary: register maps, descriptors, memory ownership, layout lowering, command completion, interrupts and recoverable errors."
---

# Host, compiler and runtime

## ABI before implementation

Define register offsets, access width, endianness, reset values, reserved bits,
read/write side effects and ordering. Distinguish write-one-to-clear, self-clearing
start bits and read-to-clear status. Specify whether multiword counters/addresses
need a snapshot or ordered write protocol.

A descriptor should state addresses, shapes, strides, formats, operation,
completion destination and ownership. Include versioning only where the actual
interface needs evolution; do not add a general schema framework to a tiny block.
Invalid values must produce explicit errors, not silent reinterpretation.

## Ownership and coherence

Define who owns buffers while a command is in flight. Host virtual addresses are
not necessarily DMA addresses; an actual driver must use the platform's mapping
and synchronization APIs. State cache-coherence assumptions and required memory
barriers. A doorbell does not by itself guarantee prior writes are visible.

Specify completion: all result writes visible, status committed and interrupt
raised in a defined order. Handle interrupt coalescing, polling races, duplicate
acknowledgements and command cancellation. Reset must define the disposition of
in-flight descriptors and buffers.

## Compiler and lowering

Map supported operators to layouts, tiling, padding, quantization and command
sequences. Keep layout conversion and host preprocessing in end-to-end latency
unless explicitly excluded by the benchmark contract. A compiler stub that emits
one handcrafted example does not demonstrate general model support.

Use a simple independent command interpreter as a reference before optimizing
the driver/runtime. For unsupported operators, either reject explicitly or use
an agreed host fallback whose cost is measured; never hide missing hardware
behind an unreported fallback.

## Verify

Test register access masks/side effects, malformed descriptors, zero/edge shapes,
buffer overlap, queue wrap, stale completions, reset and timeouts. Run the same
command stream against a reference model and the RTL interface. Preserve logs
of actual accepted commands and results, not only a high-level PASS message.
