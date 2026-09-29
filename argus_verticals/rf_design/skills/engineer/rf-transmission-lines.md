---
name: Transmission Lines and Distributed Networks
description: "Separate characteristic impedance from port references, connect delay and phase to physical assumptions, and avoid treating lumped or ideal-line models as full-wave evidence."
---

# Distinguish propagation from normalization

An ideal uniform line has ABCD entries cosh(gamma*l), Zc*sinh(gamma*l),
sinh(gamma*l)/Zc and cosh(gamma*l). Zc is its characteristic impedance; the
external reference impedances need not equal it. A matched lossless line has
S21=exp(-j*beta*l). A quarter wavelength produces -90 degrees of transmission
phase, not zero phase merely because insertion loss is zero.

The adapter's line model specifies total delay and attenuation, with propagation
alpha*l+j*2*pi*f*delay. Delay is not a geometric length unless propagation
velocity is independently known. Constant loss and nondispersive delay are
idealizations; microstrip, coplanar waveguide, connectors and waveguide modes
can have strongly frequency-dependent behavior.

Distinguish wavelength in the medium from free-space wavelength. A trace can
be electrically long at a fast edge's relevant spectral content even when a
clock's repetition frequency is modest. Return path discontinuities and mode
conversion are not captured by a single ideal two-port line.

When cascading measured and modeled sections, align physical reference planes,
frequency samples and wave references. A change of z0 does not remove a fixture's
delay. Finite phase sampling can alias wraps; extra phase points are necessary
when propagation is long. The current reader's phase checks do not independently
validate group delay, time-domain causality or an electromagnetic geometry.
