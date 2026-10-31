---
name: Interposers and Chiplet Integration
description: "Describe 2.5D/3D package interfaces and coupled constraints without promising automated advanced-package implementation."
---

# Make interfaces explicit across dice

State die roles, physical placement, connection topology, power domains,
inter-die protocol assumptions, bandwidth/latency targets and test access.
An interposer, bridge or direct stack changes routing and assembly constraints;
the technology name is not a complete interface specification.

Separate logical compatibility from physical connectivity. Lane mapping,
clocking, reference domains, power sequencing and known-good-die assumptions
need independent evidence. Protocol support does not prove an electrical
channel or manufacturable terminal geometry.

Stacking and dense integration couple heat removal, stress, warpage, supply
delivery, routing density and yield. A thermally attractive placement may
increase interconnect length or obstruct assembly/test. Describe tradeoffs
instead of optimizing one scalar while omitting the others.

The current centred-layer thermal adapter can study a restricted heat path,
not arbitrary multi-die placement, TSV arrays, microbump mechanics, protocol
verification or advanced-package process rules. Do not present its result as
a complete 2.5D/3D implementation.
