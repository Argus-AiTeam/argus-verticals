---
name: FPGA Result Acceptance
description: "Review native timing/resource reports, physical constraints and board provenance at the selected scope."
---

# Review only the claimed result

Match part/package, top ports, pin map, voltage and frequency to the actual board
documentation. Inspect warnings and native reports, not just BUILD.json.
Check that source, target and constraint copies still match. Confirm that
simulation used an independent oracle and that measured Fmax is not described
as universal timing closure. For board work, verify operator permission,
device identity, exact programmed bitstream, measurement units and setup.
No physical result is accepted from a fabricated measurement transcript.
An RTL-only result must state that implementation and physical behavior were
not established; do not demand those omitted stages merely for completeness.
