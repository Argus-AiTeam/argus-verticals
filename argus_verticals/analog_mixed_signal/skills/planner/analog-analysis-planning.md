---
name: Bounded Analog Analysis Planning
description: "Plan a small, justified set of analog analyses with predeclared observables, independent comparators and explicit model limitations."
---

# Plan the minimum informative experiment

Start from the required observable and choose a method that can answer it.
Operating point establishes bias; DC sweep examines a static characteristic;
AC examines infinitesimal response around a bias; transient follows the stated
excitation and initial conditions. None is a universal substitute for the others.
Select the requested subset rather than making all methods mandatory.

Write observable requirement IDs and numerical checks before execution.
Name the signal or ratio, units, axis position/window and acceptance interval.
For crossings, identify the relevant direction and a window that contains one
physically meaningful event. Use independent equations or justified reference
data, not fitted thresholds around the simulation's answer.

Confirm source/model availability and their valid operating range. Count the
requested condition matrix and estimate the sampling/resolution needed for
its numerical tolerances. Preserve correlations and distinguish deterministic
corners from a statistical-yield study. Defer unsupported noise, RF, extracted
layout or mixed-language analyses rather than issuing misleading work.

The Engineer owns circuit/testbench preparation and actual execution; the
Reviewer independently inspects assumptions, command output and measurement
meaning. Give both the same acceptance conditions. The plan/result format is
already supplied in the role context; do not replace it with a custom summary.
An unchanged, current result may be reused after its input copies and native
measurements pass the checker. Replanning should address a real missing
comparison or failed assumption, not create repeated analysis for its own sake.

For operating envelopes, keep the supplied specification separate from the
plan's allowed common choices. Count the complete Cartesian product plus
nominal and every required method/resolution before execution. Preserve the
fixed diagnosis/design goal and metric-unit margins; do not reinterpret a
failed design as a diagnosis or an invalid numerical study as a valid failure.
