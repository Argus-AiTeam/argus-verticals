# nanogpt_speedrun

**Purpose:** minimize wall-clock time to reach val_loss<=3.28 on modded-nanogpt (8xH100).

Optimize-kind mission on Argus's speedrun base contract with a `metric` completion gate; inherits `speedrun`'s skills (`VERTICAL_SKILL_PARENTS = ("speedrun",)`).

- `stages.py`: contract and completion checks.
- `capstone.py`: frozen-protocol and measured-result check for the final run (`argus.verticals.metric_evidence`).
- `skills/engineer/nanogpt-speedrun-h100-sota.md`.

Extras: none. Tests: `tests/skills/test_nanogpt_speedrun_vertical.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
