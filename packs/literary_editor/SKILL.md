---
name: literary_editor
description: "rewrite, expand, polish, proofread, or critique an existing literary text while preserving edit scope and source facts"
version: 0.2.0
---

# literary_editor

rewrite, expand, polish, proofread, or critique an existing literary text while preserving edit scope and source facts.

## What counts as done

### intake

Save the text to edit verbatim as `editor/source.txt` and the request as `editor/edit_brief.json` (fields under Run the checks).

### diagnose

Write `editor/review.json`: findings on the SOURCE against the goal. Do not rewrite yet.

### revision_plan

Save the plan `edit_check.py review` prints (blocking findings first, then by severity) as `editor/revision_plan.json`.

### edit

Produce `editor/edited.txt` honoring the mode and `must_keep`.

- **mode-discipline-held** — The Reviewer judged the semantic change against the stated mode and goal; every explicit must-keep segment survives verbatim.
  Evidence hint: review judgment + editor edit-check

### verify

Record what changed and why in `editor/change_summary.json`.

- **no-invented-fact** — No fact was invented in a polish/proofread; fact fidelity and edit quality are recorded as NON-blocking live judgements.
  Evidence hint: review.json fact_fidelity finding is live, not faked

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/edit_check.py' --help
python3 '<this folder>/edit_check.py' edit --project-root .
python3 '<this folder>/edit_check.py' review --project-root .
```

`editor/edit_brief.json` is an object with `mode` (`rewrite`, `expand`, `polish`, `proofread`, or `critique`), `goal`, `must_keep` (segments that must survive verbatim), and `allow_new_facts` (true by default only for `expand` and `rewrite`). The mode fixes what kind of edit is allowed: a critique edits NOTHING (`edited.txt` keeps the source text; the critique is the review); a proofread only fixes errors; an expand adds; NEVER drop a must-keep segment and NEVER invent a fact in a polish.

`edit` reads `editor/source.txt`, `editor/edited.txt`, and `editor/edit_brief.json`. Exit 0 means the edited text is non-empty and contains every `must_keep` segment (whitespace-normalized); exit 1 prints each issue: missing or malformed inputs, an empty edit, or each dropped segment. It does not judge whether the edit is good or stayed within its mode; that is the Reviewer's call ([edit-review.md](skills/reviewer/edit-review.md)).

`review` validates `editor/review.json`: `verdict` is `revise` or `done`; each finding has non-empty string `id`, `type`, `location`, `evidence`, and `suggested_action`, a `severity` of `critical`, `major`, `minor`, or `note`, a boolean `blocking`, and optional `violated_constraint`, `must_not_break` (list of strings), and `confidence` (0 to 1). `type` is `must_not_break` or `empty` (blocking edit discipline) or `edit_quality`, `fact_fidelity`, `coherence`, or `over_reach` (non-blocking craft). A blocking finding requires `revise`; no findings requires `done`. Exit 0 prints the revision plan as JSON, the content of `editor/revision_plan.json`; exit 1 prints the first problem. A valid review proves only its shape; read the source and the edit to judge it. The Reviewer cannot write the workspace: it gives its review as this JSON in its letter, and the Engineer saves it as `editor/review.json`.

## Needs

Python 3.10+; edit_check.py uses only the standard library and needs no GPU or network. The work needs the operator's source text and editing request; no other software, hardware, or license. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- reviewer: [edit-review.md](skills/reviewer/edit-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [edit_check.py](edit_check.py)
