---
name: fiction_writing
description: "write or continue original fiction narrative prose while preserving characters, world, and timeline; not a literature review or research task"
version: 0.2.0
---

# fiction_writing

write or continue original fiction narrative prose while preserving characters, world, and timeline; not a literature review or research task.

## What counts as done

### intake

- **brief-complete** — creative_brief.json fixes language, form, mode, genre, length, viewpoint and tense; nothing critical left implicit.
  Evidence hint: fiction/creative_brief.json fields non-empty

- **style-abstract** — style_profile.json is abstract, checkable features, not 'imitate author X'.
  Evidence hint: fiction/style_profile.json feature keys

- **continuation-grounded** — For mode=continuation, the existing story_state was loaded as the ground truth (not re-invented).
  Evidence hint: story_state.json present and referenced when continuing

### plan

- **chapter-goal-advances** — chapter_goal.json states a concrete goal that advances the arc (change/pressure), not a flat scene.
  Evidence hint: fiction/chapter_goal.json goal + arc link

- **plan-consistent-with-state** — For a continuation, the plan contradicts nothing in the established characters/world/timeline/open threads.
  Evidence hint: plan cross-checked against story_state.json

### draft

- **viewpoint-tense-stable** — The draft holds a single viewpoint and tense as declared in the brief.
  Evidence hint: no 1st/3rd or past/present drift in draft.md

- **language-consistent** — The draft is in the brief's language; a continuation stays in the source work's language.
  Evidence hint: draft.md language == brief.language

### state_update

- **patch-faithful** — The state_patch captures every entity/relationship/thread/foreshadowing the chapter introduced or changed, and nothing the chapter did not.
  Evidence hint: state_patch.json ops vs draft.md

- **patch-safe** — The patch applied through the engine: idempotent by patch_id, valid id references, no silent deletion of prior state, timeline still parseable.
  Evidence hint: story_state.json revision bumped + applied_patches

### review

- **continuity-findings-evidenced** — Every continuity finding is typed, severity-tagged, and cites an evidence location in the draft/state.
  Evidence hint: review.json findings[].{type,severity,location}

- **aesthetic-not-faked** — Craft/AI-flavor items are recorded as heuristic, non-blocking observations or observable proxies, not as a manufactured deterministic score.
  Evidence hint: review.json craft findings marked non-blocking

### revise

- **blocking-fixed** — Every BLOCKING continuity finding is resolved with a concrete change; no new contradiction introduced.
  Evidence hint: final.md vs review.json blocking items

- **state-matches-final** — updated_story_state.json is consistent with final.md.
  Evidence hint: updated_story_state.json vs final.md

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory. Every project file named here lives in `fiction/`.

```sh
python3 '<this folder>/fiction.py' --help
python3 '<this folder>/fiction.py' ids --state fiction/story_state.json
python3 '<this folder>/fiction.py' apply --state fiction/story_state.json --patch fiction/state_patch.json --out fiction/story_state.json
python3 '<this folder>/fiction.py' check --stage review
python3 '<this folder>/fiction.py' review
python3 '<this folder>/fiction.py' check --stage revise
```

`ids` prints the allowed state_patch ops with their required shapes and the ids a patch may reference now. `apply` is the engine the state_update items refer to: it checks the patch against [state_patch.schema.json](schemas/state_patch.schema.json), applies all ops or none, rejects a dangling id, an `add_*` over an existing id or a reused timeline `order` (there is no delete op), bumps `meta.revision`, records `patch_id` in `applied_patches`, re-checks the result against [story_state.schema.json](schemas/story_state.schema.json) and writes `--out`; an already applied `patch_id` changes nothing. Omit `--state` for the first patch of a new story. In revise, write to `--out fiction/updated_story_state.json`. Exit 0 means `--out` was written; exit 1 prints the rejected op and the referenceable ids and writes nothing: fix the patch and rerun, never hand-edit the state.

`check --stage review` reads `draft.md`, `style_profile.json` (checked against [style_profile.schema.json](schemas/style_profile.schema.json)), `creative_brief.json`, `story_state.json` (checked against [story_state.schema.json](schemas/story_state.schema.json)) and, if present, `reference_text.md`; `--stage revise` reads `final.md` and `updated_story_state.json` instead. Language is the voice card's `meta.language`, else the brief's `language`, else `zh`. It prints every finding and blocks on: a `forbidden_lexicon` term in the prose (`voice`); a negative age, a birth after `world_clock.current_year`, an `age` that is not `current_year` − `birth_year`, or a later timeline `order` with an earlier `year` (`temporal_consistency`); a run shared verbatim with `reference_text.md` of at least 24 zh characters or 12 en words, or more than half the prose copied once 40 tokens are (`verbatim_copy`; the voice card's `novelty_budget.max_verbatim_run` and `max_overlap_ratio` replace these two thresholds). AI-cliché pattern hits, `avoided_terms` and shorter copied runs are non-blocking notes to weigh in the review. Exit 0: no blocking finding; exit 1: a blocking finding, or an input missing, empty or invalid. Continuity against the prose, viewpoint, tense, language and craft are the reviewer's judgement, not this check's.

`review` checks `review.json` against [review.schema.json](schemas/review.schema.json), the finding types listed in the reviewer reference, and that a blocking finding comes with verdict `revise` and no findings with `done`; it then writes `revision_plan.json`, blocking findings first, then by severity. Exit 0 means the plan was written; exit 1 prints the reason and writes nothing.

## Needs

Python 3.10+; fiction.py uses only the standard library and needs no GPU, model or network. If the optional `opencc` package is importable, the copy check also folds traditional to simplified Chinese; without it, a copy converted wholesale between scripts is not caught. A continuation needs the operator's source text as `fiction/reference_text.md`, with its rights cleared for the use. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [chapter-drafting-and-continuation.md](skills/engineer/chapter-drafting-and-continuation.md)

- engineer: [creative-brief-and-style-profile.md](skills/engineer/creative-brief-and-style-profile.md)

- engineer: [story-and-chapter-planning.md](skills/engineer/story-and-chapter-planning.md)

- engineer: [story-state-update.md](skills/engineer/story-state-update.md)

- engineer: [targeted-fiction-revision.md](skills/engineer/targeted-fiction-revision.md)

- reviewer: [continuity-style-and-plot-review.md](skills/reviewer/continuity-style-and-plot-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [fiction.py](fiction.py)

- [references/shared/narrative-craft.md](references/shared/narrative-craft.md) — craft cards, continuity rules, review rubric

- [references/zh/style-and-anti-ai.md](references/zh/style-and-anti-ai.md), [references/en/style-and-anti-ai.md](references/en/style-and-anti-ai.md) — per-language style features and anti-AI patterns

- Voice-card presets in `references/voice_cards/`: [base.json](references/voice_cards/base.json), [classical_zhanghui.json](references/voice_cards/classical_zhanghui.json), [literary.json](references/voice_cards/literary.json), [romance.json](references/voice_cards/romance.json), [scifi.json](references/voice_cards/scifi.json), [suspense.json](references/voice_cards/suspense.json), [web_fiction.json](references/voice_cards/web_fiction.json). A chosen preset goes over `base.json` and under the work's own values (term lists accumulate); leave out the `_note` key, which the schema rejects.

- Schemas: [story_state.schema.json](schemas/story_state.schema.json), [state_patch.schema.json](schemas/state_patch.schema.json), [style_profile.schema.json](schemas/style_profile.schema.json), [review.schema.json](schemas/review.schema.json)
