---
name: prose
description: "compose or revise literary essays, memoir, or 抒情/叙事散文/随笔; not verse or plot-driven fiction"
version: 0.2.0
---

# prose

compose or revise literary essays, memoir, or 抒情/叙事散文/随笔; not verse or plot-driven fiction.

## What counts as done

### intake

Record `prose/task_envelope.json` and derive `prose/prose_brief.json`.

### plan

Declare `prose/prose_state.json` (narrative_center / observation_subject / factual_anchors / memory_boundary / paragraph_movement / ending_strategy, plus the brief's `spec`) BEFORE drafting.

### draft

Write `prose/draft.md`. NEVER invent a fact the operator did not give — keep memory and fact distinct per the declared boundary. Avoid slogan endings and template philosophizing.

### structure_check

- **prose-state-complete** — prose_state declares narrative_center/observation_subject/factual_anchors/memory_boundary/paragraph_movement/ending_strategy.
  Evidence hint: prose/structure_report.json has no structure findings

### review

- **fact-memory-is-live** — fact/memory boundary and fabrication are NON-blocking live-reviewer judgements, never mechanized; an invented fact is never silently passed as the operator's memory.
  Evidence hint: review.json fact_memory/fabrication findings are live

### revise

Write `prose/final.md` from `prose/revision_plan.json`; the final text passes the same structure check.

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory. The project files named below live in the project's `prose/`.

```sh
python3 '<this folder>/prose_check.py' --help
python3 '<this folder>/prose_check.py' brief
python3 '<this folder>/prose_check.py' structure
python3 '<this folder>/prose_check.py' review
python3 '<this folder>/prose_check.py' structure --final
```

`brief` checks `task_envelope.json` against [task_envelope.schema.json](schemas/task_envelope.schema.json) (task_id, mode, language `zh` or `en`, form, intent; a mode that works on existing text needs a `source_text` or `prior_state` reference input; the form must be a prose form) and writes `prose_brief.json`. Its `spec` (language, and `min_paragraphs`, `max_paragraphs`, `banned_words` from `output_requirements`) is what `structure` reads from `prose_state.json`; without it only emptiness is checked.

`structure` checks that `prose_state.json` declares the six fields above, none empty, and that `draft.md` (`final.md` with `--final`) meets `spec`: not empty, paragraph count (paragraphs are separated by a blank line) within bounds, `zh` text at least half Han script and `en` text at most a fifth, no banned word. It always rewrites `structure_report.json` as `{text, findings}`; exit 0 means no findings, exit 1 prints each one.

`review` checks `review.json` against [review.schema.json](schemas/review.schema.json), the prose finding types (structure, language, paragraph_count, banned_word, empty; observation, fact_memory, fabrication, movement, imagery, ending, template) and that a blocking finding comes with verdict `revise` and no findings with `done`; it then writes `revision_plan.json`, blocking findings first, then by severity. For `brief` and `review`, exit 0 means the file was written and exit 1 prints the reason and writes nothing.

Structure completeness and declared hard constraints are the only machine-checked requirements. Whether observation is concrete, fact and memory stay distinct, nothing is fabricated, paragraphs move and the ending is earned is the reviewer's judgement; see the role reference.

## Needs

Python 3.10+; prose_check.py uses only the standard library and needs no GPU. Writing needs the operator's own facts, memories and notes for memoir or essay material; public essays serve as technique reference only, with each work's rights checked. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- reviewer: [prose-review.md](skills/reviewer/prose-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [prose_check.py](prose_check.py)

- [schemas/review.schema.json](schemas/review.schema.json)

- [schemas/task_envelope.schema.json](schemas/task_envelope.schema.json)
