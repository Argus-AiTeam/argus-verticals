---
name: Digital Arithmetic and Fixed Point
description: "Specify signed arithmetic, carry/overflow, fixed-point scaling, rounding, saturation, multiplication and accumulation without accidental width loss."
---

# Arithmetic and fixed point

## Numerical contract

Record signedness, total width and fractional-bit count for every interface.
Here a signed fixed-point value with width W and F fractional bits represents
`integer_code * 2**(-F)`; do not rely on inconsistent Q-format naming conventions.
Addition requires aligned binary points. Multiplication adds operand fractional
counts. Sign-extend before arithmetic, not after a narrow intermediate overflows.

Unsigned W-bit addition needs W+1 bits for carry. A signed N-term sum of W-bit
values fits in W+ceil(log2(N)) bits; exact workload bounds can justify less.
A full product of Wa and Wb bits needs Wa+Wb bits. Saturating and wrapping
arithmetic are different operations; neither may be substituted silently.

## Example: unsigned saturation

```systemverilog
module dc_sat_add8(
    input logic [7:0] a, b,
    output logic [7:0] y,
    output logic saturated
);
    logic [8:0] extended;
    always_comb begin
        extended = {1'b0, a} + {1'b0, b};
        saturated = extended[8];
        y = saturated ? 8'hff : extended[7:0];
    end
endmodule
```

This carry rule is not signed overflow detection. Signed addition overflows when
equal-sign operands produce an opposite-sign result; clamp to the appropriate
signed maximum/minimum, not an unsigned all-ones constant.

## Precision and structures

When discarding fractional bits, define truncation direction and rounding mode.
Arithmetic right shift of a negative two's-complement value rounds toward negative
infinity, unlike truncation toward zero. For round-to-nearest-even, track the
guard bit, sticky bits and retained LSB; increase magnitude only under the
specified tie rule, then handle possible overflow. Test negative ties explicitly.

Ripple, carry-select and prefix adders trade area, wiring and latency. FPGA carry
chains and DSP inference can beat hand-coded structures. Pipelining a multiplier
changes interface latency; it is not a free timing fix. Tree reduction reduces
logic depth while serial accumulation shares hardware at a throughput cost.

## Verify

For the example, exhaust 65,536 pairs against integer `min(a+b,255)`.
For signed/fixed-point blocks, test both extremes, zero, -1, cross-zero cases,
half-LSB ties, largest non-overflowing results, and the first overflowing result.
Compare quantized integer codes to a wider independent model before comparing
real-valued error. Report error bounds and overflow frequency, not only MSE.
