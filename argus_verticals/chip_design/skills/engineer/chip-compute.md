---
name: Chip Compute and Numerical Architecture
description: "Map workloads to accelerator compute: roofline/Amdahl limits, dataflow, array utilization, fixed-point semantics, resource sharing and microarchitectural verification."
---

# Compute and numerical architecture

## Workload to operations

Freeze operators, tensor shapes, batches, sparsity assumptions and quality floor.
Specify whether one MAC is counted as one operation or two. Separate prefill and
decode for language-model workloads; their reuse and bottlenecks differ.
Derive operation counts before selecting an array: dense matrix multiplication
M-by-K times K-by-N needs M*N*K MACs, excluding preprocessing and output handling.

With P effective MAC lanes at frequency f, peak rate is P*f MAC/s. Useful rate
also depends on shape packing, bubbles, memory stalls and pipeline fill/drain.
Report each utilization loss instead of treating peak as measured performance.
Amdahl bounds end-to-end speedup when only a fraction of host work is accelerated.

## Architecture alternatives

Systolic arrays amortize communication on regular tiles but lose efficiency on
small/irregular shapes. SIMD lanes tolerate more operation diversity at control
cost. Serial/folded datapaths share multipliers/accumulators and reduce area at
extra cycles. Spatial replication helps only if memory and outputs sustain it.

Choose weight-, output- or input-stationary dataflow from traffic/capacity
calculations. Keep a lifetime table for accumulators, operands, conversion units
and temporary buffers. Resource sharing can add mux delay and routing; quantify
that cost rather than calling it an automatic PPA improvement.

## Numerics

Define signedness, scale/zero-point, accumulation width, requantization, rounding,
saturation and activation ordering. For int8 signed operands, an individual
product fits in 16 bits; accumulation width additionally depends on reduction
length and bias. Do not assume 32 bits suffices for every K.
Track both integer-code agreement and end-task quality; a numerically plausible
distribution can still violate the exact reference semantics.

## Example architecture study

For a 16x16x64 matmul tile, compute 16,384 MACs. At 16 MAC/cycle the compute-only
lower bound is 1,024 cycles before fill/drain and stalls. Quantify operand/output
traffic under the chosen buffering and reuse scheme, then take the larger compute
or bandwidth bound. These are analytical estimates, not simulation or PPA results.

## Verification and evidence

Test minimal, ragged and non-multiple-of-lane shapes; all-zero/extreme values;
accumulator overflow; stalled output and partial tiles. Check counters against
the independent operation count. Preserve model inputs and assumptions in
`design/ARCHITECTURE.md` and `design/MEMORY_MODEL.json`. When implementing RTL,
use the inherited arithmetic/pipeline guides and actual cycle-level evidence.
