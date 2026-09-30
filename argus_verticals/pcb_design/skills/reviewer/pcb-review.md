---
name: PCB Independent Review
description: "Verify native input identity, engineering assumptions and manufacturing geometry without overstating physical conclusions."
---

# Independently inspect the claim

Read the original request and canonical contract before the Engineer's
conclusion. Check that selected operations, error/warning bounds, layer list
and drill counts were not weakened. Run the supplied checker from the actual
project; inspect retained native JSON and logs, not only the summary.

Confirm the project settings and local library closure match current sources.
Inspect component/pad mapping, power/return assumptions, outline and holes at
the level required by the task. Native replay establishes consistency with
KiCad; it does not make the local library or configured rules authoritative
engineering truth.

Distinguish no findings from allowed diagnostic findings, and unperformed
checks from passed checks. Fabrication-only export must not be described as
ERC/DRC acceptance. Explain unsupported inputs and absent datasheet, fab,
SI/PI, assembly or physical evidence. Reject invented completion records and
source edits outside the user's permission.

When zones are present, require an explicit native refill from original inputs.
Check that the command records point to the same working project for DRC and
exports, and that the independent replay covers the filled board, zone data and
manufacturing geometry. Report empty or unexpectedly reduced fills; positive
polygon area alone proves neither connection nor an adequate return path.
Do not mistake `refill-rules.rpt` for the selected post-fill DRC result.
