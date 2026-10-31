---
name: modern_poetry
description: "compose or revise modern free verse/prose poems without classical prosody checks; enforce only declared hard constraints"
version: 0.2.0
---

# modern_poetry

compose or revise modern free verse/prose poems without classical prosody checks; enforce only declared hard constraints.

## What counts as done

### intake

Take from the request its language (`zh` or `en`), form (free verse, prose poem, lyric; 现代诗、自由诗、散文诗、抒情诗), intent, and the hard constraints it declares (line count, minimum or maximum lines, banned words). A task on an existing poem (continue, rewrite, expand, polish, proofread, critique) needs that poem from the request. Classical forms with 平仄/韵 and narrative forms are outside this pack.

### plan

Before composing, write `poetry/form_spec.json` with the poem's language and only the hard constraints the request declares (format under Run the checks) and plan the poem's central image or tension.

### compose

Write `poetry/draft_poem.txt`. Avoiding meaningless line breaks and cliché imagery is the writer's judgement, not a machine check.

### form_check

- **hard-constraints-met** — The draft meets every DECLARED hard constraint (language, line count, banned words); no aesthetic claim is made here.
  Evidence hint: poetry/form_report.json has no findings

### review

- **craft-is-live** — Imagery/lineation/tone/cliché are NON-blocking live-reviewer judgements, never a mechanized or scored capability.
  Evidence hint: review.json craft findings marked non-blocking

### revise

Work through the findings in the order `poem_check.py review` prints them, keeping each `must_not_break`, and write `poetry/final_poem.txt`; it must pass the same hard-constraint check as the draft.

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/poem_check.py' --help
python3 '<this folder>/poem_check.py' draft --project-root .
python3 '<this folder>/poem_check.py' review --project-root .
python3 '<this folder>/poem_check.py' final --project-root .
```

`poetry/form_spec.json` is a JSON object: `language` (`zh` or `en`, the request's language) plus only what the request declares, `line_count`, `min_lines`, `max_lines` (integers) and `banned_words` (a list of strings); a key left out is not checked. `draft` checks `poetry/draft_poem.txt` against it and writes `poetry/form_report.json` as `{poem, findings}`, each finding `{type, severity, line, detail}`, and invalid inputs leave no report; `final` checks `poetry/final_poem.txt` the same way and writes nothing. Lines are the non-blank lines and an empty poem always fails; `zh` needs at least half of the non-space characters to be Han, `en` allows at most a fifth; a banned word is found anywhere inside a line, and only listed words are caught. `review` checks `poetry/review.json` against the format in [modern-verse-review.md](skills/reviewer/modern-verse-review.md), including that hard-constraint findings are blocking and craft findings are not, and prints its findings in the order to revise them: blocking first, then by severity. Exit 0 means no finding or a valid review; exit 1 prints each issue, including a missing or malformed input. A pass says nothing about whether the poem is good: imagery, lineation, tone, and cliché beyond the list are the reviewer's reading.

## Needs

Python 3.10+; poem_check.py uses only the standard library and needs no GPU, model, corpus, or license. Reference poems the request supplies may be read and cited only as the request permits; most modern verse is in copyright, so do not reproduce it beyond that. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the reference are created by the task.

- reviewer: [modern-verse-review.md](skills/reviewer/modern-verse-review.md)

## Supporting files

- [LICENSE](LICENSE)

- [poem_check.py](poem_check.py)
