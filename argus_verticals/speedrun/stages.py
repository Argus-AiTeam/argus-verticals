"""Speedrun-vertical stage definitions.

A vertical for **quantitative optimization missions** with a wall-time
budget — kernel optimization, training-script speedrun, autoresearch
benchmarks like ``nanochat_autoresearch`` and SOL-ExecBench.

There is no paper. There is one number to minimize (or maximize) under
a hard wall-clock budget, scored by a fixed harness, evaluated over N
seeds. The verdict is mechanical, not narrative.

The 4 stages:

1. **setup**: pin the target (script to attack), the harness
   (``solutions/lib.py``), the reference baseline scores, and the
   hardware budget. Output: ``mission/SETUP.md``.

2. **optimize**: produce attempts under ``attempts/<name>/train.py``,
   each a self-contained training script that fits the harness
   contract. Output: at least one such script per round.

3. **measure**: run each attempt for N seeds, score via the harness,
   record per-seed rows in ``attempts/<name>/results.csv``. Output:
   one row per (attempt × seed).

4. **report**: aggregate attempt × repeat rows into a single
   ``RESULTS.md`` table comparing the mission metric / wall time vs the
   reference baselines, with honest CI. No prose beyond a one-paragraph
   "what changed and what didn't" per attempt.

Compared to the research vertical (which has 8 stages, paper artifacts,
literature gates, reviewer checklists per stage), this vertical is
deliberately *small* — most of the supervisor work happens inside the
single ``optimize`` stage where engineer iterates code, and the
mechanical ``measure`` + ``report`` stages take seconds. This is the
right shape for "the agent writes code, the harness scores it" tasks
where there is nothing to write up.
"""
from __future__ import annotations

from pathlib import Path

from argus.skills.stage_machine import ChecklistItem
from argus.verticals.optimization_base import (
    OPTIMIZATION_CHECKLIST_ITEMS,
    OPTIMIZATION_STAGE_ORDER,
)

# Plugin contract read by Argus (argus/verticals/_registry.py): the API
# version and purpose advertise this vertical to the Manager's menu, the skills
# root is seeded like a built-in's, and parents' skill trees are seeded first.
# The stage/checklist contract itself is argus/core/vertical_contract.py.
ARGUS_VERTICAL_API_VERSION = 1
VERTICAL_PURPOSE = (
    "single-metric script/benchmark optimization under a wall-clock budget: "
    "setup, optimize, measure, report; no paper"
)
VERTICAL_SKILLS = Path(__file__).resolve().parent / "skills"
VERTICAL_SKILL_PARENTS: tuple[str, ...] = ()

STAGE_ORDER = list(OPTIMIZATION_STAGE_ORDER)

__all__ = [
    "STAGE_ORDER",
    "CHECKLIST_STAGE_ORDER",
    "CHECKLIST_ITEMS",
    "role_banner",
    "completion_gate",
    "ROUND_POLICY",
    "stage_completion_issues",
]


# ===========================================================================
# System (B) — markdown stage checklists for the speedrun vertical
# ===========================================================================
#
# These feed ``argus.skills.stage_machine`` (the markdown checklist
# that drives the planner/engineer/reviewer round loop) via the optional-hook
# contract in ``argus.verticals._base``. The research vertical re-exports
# the paper floor; the speedrun vertical declares a 4-stage, metric-agnostic
# checklist instead — there is no paper, one number to move the right way
# under a fixed wall-clock budget, whatever that number is (val bpb, kernel
# speedup/SOL, latency, accuracy, …).
#
# The items are GENERIC across optimization missions and are owned by Argus's
# bridge module ``argus.verticals.optimization_base``
# (``OPTIMIZATION_CHECKLIST_ITEMS``): the deliverable/eval contract is pinned
# at ``setup``, the candidate is produced and screened at ``optimize``, the
# repeat-mean / budget measurement happens at ``measure``, and the head-to-head
# baseline comparison is the ``report``. ``math_synth`` (built in) and the
# other optimization verticals here specialise the same table. Mission-specific
# nouns (the editable file, the scorer, the metric name, the named baseline)
# come from the operator objective / MISSION.md, not hard-coded here.

#: System-(B) stage order for the speedrun vertical (mirrors STAGE_ORDER).
CHECKLIST_STAGE_ORDER: tuple[str, ...] = OPTIMIZATION_STAGE_ORDER

#: System-(B) per-stage markdown checklist items: the framework's canonical
#: optimization table, copied into this vertical's own ``dict`` so a
#: specialisation never mutates the bridge's constant.
CHECKLIST_ITEMS: dict[str, tuple[ChecklistItem, ...]] = dict(OPTIMIZATION_CHECKLIST_ITEMS)

#: Speedrun missions are done on a metric verdict, not a paper-submission gate.
completion_gate = "metric"
# Round guards (Argus core/round_policy.py; an Argus without per-vertical round
# policies ignores this). Metric optimization is a long loop: change the
# script, re-measure, compare. Rounds without a better score are part of
# searching, so the soft round window is off and the Reviewer's explicit
# no-progress streak decides (6 verdicts). A Reviewer that stops giving any
# progress judgement is caught after 200 rounds.
ROUND_POLICY = {
    "stall_threshold": 6,
    "no_progress_threshold": 2,
    "soft_round_limit": 0,
    "hard_escalate_rounds": 200,
}
MISSION_KIND = "optimize"


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    from argus.verticals.metric_evidence import EvidenceError, validate_speedrun_evidence

    issues: list[str] = []
    if stage in {"measure", "report"}:
        try:
            validate_speedrun_evidence(project_root)
        except EvidenceError as exc:
            issues.append(str(exc))
    if stage == "report":
        report = project_root / "RESULTS.md"
        if not report.is_file() or report.stat().st_size <= 0:
            issues.append("report requires non-empty RESULTS.md")
    return tuple(issues)


def role_banner(role: str = "engineer") -> str:
    """Top-of-prompt HARD-OVERRIDE banner for the speedrun vertical.

    The default planner/reviewer/engineer prompts bake in the research-paper
    pipeline (research gate, literature grounding, decision gates, paper draft/
    review/submission, and stage rollback to upstream paper stages). In a
    speedrun (numeric-optimization) mission those assumptions are wrong and
    actively harmful — the planner will refuse to start ("still at the research
    gate"), and the reviewer/planner will roll the state machine back to
    ``research``. This banner is injected at the very TOP of each agent prompt
    so it supersedes all of that framing.

    It is intentionally generic (no hard-coded file names): the concrete
    editable file and scorer come from the operator objective + special
    prompts, so the same banner serves any speedrun task.
    """
    role_norm = (role or "").strip().lower()
    common = (
        "## INVENT — find NEW mechanisms; do not just re-tune existing knobs\n"
        "This mission breaks a record by INVENTION: a new fused kernel, an FP8 / "
        "low-precision GEMM, a new optimizer / attention / precision scheme, "
        "restructured numerics. A parameter reshuffle of the EXISTING recipe (a "
        "step-count tweak, an LR / momentum nudge, moving an existing split) is NOT "
        "an invention and is the FAILURE MODE to avoid. Work in three moves, IN ORDER:\n"
        "  1. PROFILE FIRST — before tuning anything, measure WHERE the wall-clock "
        "goes at the op / kernel level (per-module or per-kernel time, which ops are "
        "unfused, which GEMMs are NOT in FP8, where HBM traffic dominates). Record the "
        "top costs in `research/PROFILE.md`. Invention targets are invisible until you "
        "profile.\n"
        "  2. RESEARCH a technique to attack the top cost — web search, papers, public "
        "kernel/library docs for a GENERAL method (FP8 GEMM patterns, fused Triton "
        "kernels avoiding HBM round-trips, optimizer / Newton-Schulz / noise methods, "
        "attention-kernel variants). Note it in `research/TECHNIQUE_NOTES.md`.\n"
        "  3. IMPLEMENT it yourself as a real NEW mechanism — usually editing "
        "`triton_kernels.py`, not just `train.py` scalars — then score it. A bold, "
        "honestly-measured mechanism that does not YET win is worth FAR more than a "
        "trivial tweak that merely scores.\n"
        "ANTI-CHEAT (HARD): research GENERAL techniques only. You MUST NOT search for, "
        "open, or copy the ANSWER to THIS task — the modded-nanogpt leaderboard or any "
        "record / write-up beyond your given starting point, or any published 'best' / "
        "'optimized' solution to this exact speedrun. General method = ALLOWED; this "
        "task's published solution = DISQUALIFYING.\n"
        "\n"
        "## THE WHOLE MISSION IS OPTIMIZE — hard override of everything below\n"
        "Lean numeric-optimization loop, NOT a research paper. NO paper / draft / "
        "review / submission / publication stages; the only stages are `run` (edit "
        "+ score) and `analysis`; missing paper files are EXPECTED, never a defect "
        "— the stage is never rolled back to research/plan (stage transitions are the "
        "Manager's, not yours), never rebuild a paper-stage literature "
        "requirement (short `research/PROFILE.md` and `research/TECHNIQUE_NOTES.md` are fine). "
        "Score only with the frozen scorer the objective names. Run BASIN-HOPPING + "
        "CO-TUNING, not greedy hill-climb: snapshot the lowest-ever VERIFIER-measured "
        "metric as the GLOBAL BEST (the floor the mission will report, never lost), but develop an "
        "ACTIVE LINE that may sit ABOVE the floor while a mechanism matures over "
        "several rounds. Done only when the metric target is met or the budget is "
        "spent.\n"
    )
    role_line = {
        "planner": (
            "- As PLANNER: stay in the run stage. Your FIRST mission on a fresh recipe "
            "is PROFILE — produce `research/PROFILE.md` (an op/kernel-level time "
            "breakdown naming the top cost to attack). After that, every line you "
            "queue ATTACKS a profiled top cost with a NEW mechanism (research a "
            "technique, then implement it in the kernel / precision path) — NOT another "
            "tweak of an existing knob. A pure parameter line (step count, LR, split "
            "timing) is the LOWEST-value mission and must NEVER be your opener or your "
            "basin-hop target. Develop the ACTIVE LINE over several co-tuning rounds; "
            "when it stalls (~3 rounds <0.001 or failing), basin-hop to a DIFFERENT op "
            "to attack or a DIFFERENT technique. A maturing mechanism may sit ABOVE the "
            "global best — never kill it after one losing round. Do NOT queue paper / "
            "paper / rollback tasks. Judge project_done purely on the metric.\n"
        ),
        "reviewer": (
            "- As REVIEWER, you are also the INNOVATION COACH, and you run a "
            "BASIN-HOPPING + CO-TUNING search — NOT a greedy single-point "
            "hill-climb. Your job is to keep the verified floor safe while pushing "
            "the search into structurally NEW regions of the design space. "
            "Specifically:\n"
            "  * GLOBAL BEST vs ACTIVE LINE: the lowest-ever VERIFIER-measured mean "
            "metric is the GLOBAL BEST — keep it snapshotted and NEVER lose that "
            "floor. But do NOT demand that every experiment restart from the "
            "global-best SHA; that greedy re-anchoring is exactly what traps the "
            "loop in a local optimum. Track a separate ACTIVE LINE the engineer is "
            "currently developing, which may sit slightly ABOVE the global best "
            "while it matures.\n"
            "  * MATURATION WINDOW: a structural / optimizer / architecture change "
            "usually scores WORSE on round 1 because its supporting hyperparameters "
            "(LR, init, warmup, schedule) do not fit yet, and only wins after 2-4 "
            "rounds of CO-TUNING. Give every new direction a maturation window of "
            "several rounds before judging it; NEVER declare a bold direction dead "
            "after a single losing round — that is the central mistake.\n"
            "  * COMBINE coordinated changes: when a structural change and the "
            "hyperparameters that support it express ONE idea, accept them as ONE "
            "candidate. Do not force one-knob-at-a-time on a method-level move.\n"
            "  * BASIN-HOP when nibbling: if the last ~3 rounds each improved the "
            "global best by <0.001 (or failed), the recipe is in a LOCAL OPTIMUM. "
            "Stop approving further perturbations of it and, in next_action, DEMAND "
            "a NEW active line from a STRUCTURALLY DIFFERENT region — a different "
            "depth/width trade, a different attention scheme, a different optimizer "
            "regime, a different token/step-budget split, a curriculum, a different "
            "normalization/residual scheme. Develop THAT for several rounds EVEN IF "
            "it is temporarily worse than the global best; you are exploring, not "
            "climbing.\n"
            "  * REVERT means revert the ACTIVE LINE's last step — not snap all the "
            "way back to the global-best SHA for the next idea. Always snapshot the "
            "global best so exploration never loses ground, but let the next idea "
            "continue from where the active line is.\n"
            "  * BIAS TO BOLD: at least HALF of your next_action recommendations "
            "must be structural / method-level explorations (new architecture, "
            "optimizer, or training paradigm), not regularizer/init/LR nibbles — the "
            "nibbles are nearly exhausted and the remaining gains live in a "
            "different region of the design space.\n"
            "  * NEVER accept 'no changes / objective complete' while budget remains "
            "and the metric can still drop, and treat a properly measured-and-"
            "reverted bold experiment as GOOD process, not failure. Do NOT flag "
            "missing research/paper files, apply paper/contribution criteria, or "
            "recommend rollback.\n"
        ),
        "engineer": (
            "- As ENGINEER: PROFILE before you tune — if `research/PROFILE.md` is "
            "missing or stale, produce it (op/kernel-level time breakdown) FIRST. Then "
            "each turn attempt the boldest NEW mechanism you can implement correctly to "
            "attack the top profiled cost: research a general technique, implement it "
            "(usually in `triton_kernels.py`, not just `train.py` scalars), and score "
            "it; a multi-round mechanism temporarily BEHIND the floor is EXPECTED and "
            "good. Always snapshot the verified GLOBAL BEST so the floor is never lost; "
            "'revert' rolls back the active line's last step, not a snap-back to the "
            "floor. Do NOT default to a trivial one-knob tweak just to bank a score — "
            "that is a wasted round. Keep short `research/PROFILE.md` / "
            "`research/TECHNIQUE_NOTES.md`; do NOT write paper/draft files.\n"
        ),
    }.get(role_norm, "")
    return common + role_line + "\n"
