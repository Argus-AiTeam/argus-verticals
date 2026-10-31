---
name: PCB Schematic Intent
description: "Read electrical connectivity and power intent rather than treating a clean ERC report as circuit correctness."
---

# Connectivity before presentation

Trace each external interface from connector pin number through protection,
termination and functional device pins. Distinguish signal labels, hierarchical
ports and global power labels; similar printed names do not establish native
connectivity. Check bus expansion and intentionally unconnected pins.

Pin electrical types determine what ERC can detect. A passive symbol may hide
output contention that a correctly typed driver would expose. Power-input pins
need a genuine source/drive convention; do not scatter power flags merely to
remove warnings. Explain intended supplies, enables, reset defaults and startup
states using component documentation.

Schematic-board parity checks link symbol identity, reference, footprint and
net assignment. They cannot validate a manufacturer's pin function or prove
that the chosen circuit topology meets the requirement. Review multi-unit
parts, hidden power pins, differential polarity and connector mating views.

When the task is diagnostic, preserve defects and report their locations.
Changes to net names, pin types, no-connect marks or severity settings are
design changes requiring a reason, not acceptable ways to clean a report.
