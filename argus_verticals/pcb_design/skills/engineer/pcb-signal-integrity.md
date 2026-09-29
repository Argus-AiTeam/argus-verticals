---
name: PCB Mixed-Signal and Fast Interfaces
description: "Reason about edge rates, coupling and reference continuity while separating PCB checks from SI/PI and RF solvers."
---

# Edge rate sets the interconnect problem

Compare propagation delay with the fastest relevant transition, not just clock
frequency. Transmission-line behavior depends on source impedance, termination,
load, topology and return geometry. Board length matching is not equivalent to
electrical delay matching across differing layers or packages.

For differential interfaces, inspect polarity, pair separation, imbalance,
stubs, via transitions and reference changes. State whether a skew constraint
is intra-pair or inter-lane and what package/connector contributions are included.
Native spacing or length checks do not establish an eye opening.

Mixed-signal partitions should control actual return currents rather than
blindly split ground. Review ADC reference/drive paths, quiet bias nodes,
clock coupling, switching-current loops and connector shield strategy.
High-impedance nodes can be sensitive to leakage and contamination as well as
capacitive coupling.

EMC, ESD, antennas and RF launches need physical constraints and appropriate
models or measurements. This vertical may reason about them and preserve
requirements; its initial KiCad execution does not perform field solving,
calibration, emissions testing or compliance certification.
