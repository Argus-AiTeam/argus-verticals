---
name: Inverters and Motor Drives
description: "Bridge modulation, bidirectional energy, DC-link behavior and machine/control boundaries."
---

# Separate power-stage and machine claims

Identify whether conversion is DC-AC, AC-DC or bidirectional, and define the
source/sink behavior of the DC link. Regeneration can raise link voltage when
the source cannot absorb energy. A resistive load is not a motor or grid model.

Bridge modulation, dead time, current sensing and switching-device models
affect distortion and loss. Torque/speed conclusions additionally require an
applicable machine model, parameter sources and control definitions.
Saturation, position error, field weakening and mechanical dynamics introduce
constraints absent from a simple electrical bridge.

Do not infer grid compatibility, motor protection or safe physical operation
from a generic PWM trace. These topics are knowledge only in the first
release; the native Buck/Boost adapter does not execute inverters, grid
interfaces, motor control or physical equipment.
