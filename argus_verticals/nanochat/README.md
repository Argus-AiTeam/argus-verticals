# nanochat

**Purpose:** minimize val_bpb on the nanochat train.py (bits-per-byte, ~300s, 1 GPU).

Optimize-kind mission on Argus's speedrun base contract (`argus_skill.verticals.optimization_base`) with a `metric` completion gate. Ships no `skills/` of its own and deliberately does not inherit the H100-specific speedrun traces; the search-altitude hook steers candidates toward mechanism-changing axes instead of re-sweeping a saturated knob.

- `stages.py`: contract, role banners, `search_altitude_context`, collaborative-contract helpers.

Extras: none. Tests: `tests/test_nanochat_altitude.py`, `tests/test_nanochat_collaborative_contract.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
