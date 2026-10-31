---
name: Converter Loss and Thermal Accounting
description: "Source signs, conduction/switching loss, stored energy, efficiency and thermal-model boundaries."
---

# Close the energy account before interpreting losses

Use SPICE's passive sign convention: delivered input power is negative
source voltage times source current. Over a transient interval,
input energy equals load energy plus dissipation plus the change in stored
energy. Charging or discharging L/C is not an efficiency failure.

Separate winding loss, capacitor ESR, switch conduction, rectifier loss,
switching charge, driver power, magnetic core loss and auxiliary consumption.
Integrating a simplified device's terminal power cannot recover omitted
capacitance, recovery or thermal behavior.

Report the averaging interval, conduction mode and whether periodic steady
state was established. Transient output/input energy ratios can exceed one
while storage discharges and should not be labeled steady efficiency.
Thermal resistance, spreading and interface conditions need appropriate
package/board evidence; an electrical loss estimate is not a junction-temperature result.
