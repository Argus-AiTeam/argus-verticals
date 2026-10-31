---
name: medical
description: "biomedical and pharmaceutical evidence execution: target-disease mechanisms, human genetics, preclinical translation, clinical trials, safety, failed programs, competitive pipelines, and auditable non-diagnostic decision dossiers with independent review; not a generic paper pipeline"
version: 0.2.0
---

# medical

biomedical and pharmaceutical evidence execution: target-disease mechanisms, human genetics, preclinical translation, clinical trials, safety, failed programs, competitive pipelines, and auditable non-diagnostic decision dossiers with independent review; not a generic paper pipeline.

## What counts as done

### scope

- **scope.medical-scope** — The target, disease, subtype or population, decision question, date bounds, exclusions, and non-diagnostic use are explicit; the request contains no patient-identifying information.
  Evidence hint: a target-disease scope record with population, decision boundary, time window, exclusions, and research-only purpose

- **scope.medical-identity** — Submitted and canonical target and disease identities, aliases, species, molecular level, biomarker context, and unresolved ambiguity are recorded without silently merging genes, proteins, pathways, drugs, indications, or disease subtypes.
  Evidence hint: submitted terms, canonical identifiers or explicit unresolved status, alias provenance, and disambiguation decisions

### retrieve

- **retrieve.medical-source-plan** — Source selection, exact queries, date bounds, deduplication, full-text needs, update policy, and stop conditions are explicit before synthesis.
  Evidence hint: source/query registry covering PubMed, ClinicalTrials.gov, selection rules, provenance fields, and infrastructure-failure treatment

- **retrieve.medical-provenance** — Every retrieved record preserves source type, source identifier, canonical URL, exact query, retrieval time, raw response, normalized fields, and the raw response file each evidence row consumed.
  Evidence hint: query journal, immutable raw responses, normalized evidence JSONL, and source-local raw_artifact paths

- **retrieve.medical-failures** — Provider, transport, parsing, rate-limit, resource, and interrupted records remain separate from biomedical evidence and do not count as negative target-disease results.
  Evidence hint: retained infrastructure-failure rows with source, request, time, error class, and retryability

### normalize

- **normalize.medical-comparability** — Source and scope fields are distinct, and any evidence comparison aligns or explicitly distinguishes model or population, disease subtype, biomarker, treatment line, intervention, comparator, endpoint, follow-up, sample size, registry update, and actual data cutoff.
  Evidence hint: row-level normalized fields and explicit non-comparability notes for mismatched studies or trials

### analyze

- **analyze.medical-evidence-strata** — The analysis proportionally covers mechanism, human genetics, preclinical, clinical, safety, failed-program, and contradictory evidence needed by the decision rather than treating publication count as evidence strength.
  Evidence hint: a question-driven evidence matrix with applicable strata, missing strata, and explicit evidence ceilings

- **analyze.medical-claim-ceiling** — Mechanism, association, target engagement, efficacy, safety, and causal claims remain at or below the strongest directly inspected evidence; metadata, registration, prediction, and preclinical results are not promoted into clinical conclusions.
  Evidence hint: claim-by-claim evidence class, source support, uncertainty, and maximum defensible wording

- **analyze.medical-conflicts** — Contradictory results, failed programs, null findings, missing sources, and alternative explanations are retained and analyzed rather than removed by convenient source selection.
  Evidence hint: conflict and gap ledger linked to both supportive and opposing records

### review

- **review.medical-source-support** — Each material conclusion is supported by the cited source at the stated scope; PubMed metadata is not described as full-text review and trial registration is not described as efficacy evidence.
  Evidence hint: independent claim-source checks against primary text or exact registry fields, with unresolved full-text needs marked

- **review.medical-numeric-fidelity** — Numbers, units, sample sizes, phases, statuses, endpoints, dates, follow-up, registry updates, and data cutoffs match their source and are not compared across incompatible study contexts.
  Evidence hint: a source-located check of every decision-relevant number and trial field

### deliver

- **deliver.medical-nondiagnostic-boundary** — The delivery is explicitly limited to research and portfolio decisions, contains no patient-specific diagnosis or treatment selection, and does not imply that Argus designed or clinically validated a new drug.
  Evidence hint: research-use statement plus a scan for patient-specific or prescriptive claims

- **deliver.medical-auditability** — The final dossier includes the scope, query history, raw-source links, normalized evidence ledger, comparison matrix, memo, unresolved gaps, cumulative infrastructure failures, and independent review state.
  Evidence hint: the complete dossier with inspectable source IDs, raw response files, and the independent review's conclusion

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/dossier.py' --help
python3 '<this folder>/dossier.py' --project-root . --target 'EGFR' --disease 'non-small cell lung cancer' --disease-alias 'NSCLC' --live
python3 '<this folder>/dossier.py' --project-root . --target 'EGFR' --disease 'non-small cell lung cancer' --pubmed-fixture <esummary.json> --clinical-trials-fixture <studies.json>
python3 '<this folder>/dossier.py' --project-root . --check
```

Building queries PubMed (E-utilities esearch and esummary) and ClinicalTrials.gov (API v2) with `--live`, or reads saved responses instead (`--pubmed-fixture` takes a PubMed esummary JSON, `--clinical-trials-fixture` a ClinicalTrials.gov v2 studies JSON). It writes `medical/scope.json`, appends `medical/queries.jsonl` and `medical/evidence_history.jsonl`, keeps every raw response under `medical/raw/pubmed/` and `medical/raw/clinical_trials/`, records source failures in `medical/infrastructure_failures.jsonl`, and rewrites `medical/evidence.jsonl` (current records, one per source ID), `medical/evidence_matrix.csv`, `medical/target_disease_memo.md` (an evidence inventory, not a conclusion) and `medical/review.json`. It refuses a scope that differs from the existing `medical/scope.json`. It prints a JSON summary; exit 0 means at least one source returned usable data, exit 2 means none did (the failures are recorded, not evidence) or the input was invalid.

`--check` validates the delivered dossier's structure: `scope.json`, `queries.jsonl`, `evidence.jsonl`, `evidence_matrix.csv`, `target_disease_memo.md` and `review.json` exist under `medical/`; the scope names a target and a disease; `evidence.jsonl` is non-empty and every row is a valid record (required fields present, `record_id` = `source_type:source_id`, https URL, non-negative sample size, no result direction without posted results) whose `raw_artifact` is an existing file inside the project; the matrix has one row per record; the memo keeps the sentence "not diagnosis or treatment advice"; `review.json` has a boolean `certified`; every raw file listed in `queries.jsonl` exists inside the project. Exit 0 prints a confirmation; exit 1 prints each issue. It does not judge claims, comparability, or whether the review passed.

`medical/review.json` holds the independent review state: building resets it to `{"schema_version": 1, "status": "pending_review", "certified": false}` and moves the previous one into `medical/review_history.jsonl`; the Reviewer records its conclusion there, keeping `certified` a boolean. Rebuilding also regenerates the memo and matrix, so keep written analysis in other files or rebuild before writing it.

## Needs

Python 3.9+; dossier.py uses only the standard library and needs no GPU. `--live` needs outbound HTTPS to eutils.ncbi.nlm.nih.gov and clinicaltrials.gov (public, no key; NCBI usage limits apply). Claims that need methods, numbers, or context beyond metadata need access to the full-text publications or other primary sources, and paid sources or private data need the operator's authorization. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [target-disease-research.md](skills/engineer/target-disease-research.md)

- manager: [medical-manager.md](skills/manager/medical-manager.md)

- planner: [medical-planning.md](skills/planner/medical-planning.md)

- reviewer: [medical-evidence-review.md](skills/reviewer/medical-evidence-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [dossier.py](dossier.py)
