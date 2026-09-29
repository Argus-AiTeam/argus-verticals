---
name: PCB Placement and Routing
description: "Preserve connectivity, mechanical constraints and current-return paths while choosing local layout improvements."
---

# Place around electrical and mechanical constraints

Fix outline, mounting holes, keepouts, connector access and critical component
orientation before optimizing trace length. Place decoupling relative to the
actual supply/return loop, not simply close in Euclidean distance. Separate
thermal, noisy-switching and sensitive nodes based on current paths.

Route power and fast transitions with their returns in mind. Avoid crossing a
reference discontinuity; layer changes may require a nearby return connection.
Differential pairs still need a common reference and balanced transition
geometry. A short signal over a poor return can be worse than a slightly longer
continuous-reference route.

Check unrouted connections, shorts, widths, clearances, via connectivity and
edge geometry with actual native DRC. Inspect neck-downs, pad entry, copper
slivers and connector escape patterns in context. Native rules detect configured
geometry violations, not whether a topology is electrically wise.

Do not refill zones or rewrite a user's board during a read-only task. The
initial adapter rejects zone-bearing boards rather than treating stale stored
fill as newly validated copper. Report that boundary explicitly.
