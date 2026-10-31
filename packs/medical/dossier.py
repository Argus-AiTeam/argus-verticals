"""Build or check a target-disease evidence dossier whose every claim traces to its source.

Standard library only; adapted from Argus's medical evidence, connectors and dossier modules.
Usage: python3 dossier.py --help
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Evidence records ------------------------------------------------------------


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _strings(value: Any) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for item in _sequence(value):
        text = _text(item)
        folded = text.casefold()
        if text and folded not in seen:
            seen.add(folded)
            values.append(text)
    return tuple(values)


def _join(values: Sequence[Any]) -> str | None:
    texts = _strings(values)
    return "; ".join(texts) if texts else None


@dataclass(frozen=True)
class MedicalScope:
    target: str
    disease: str
    target_aliases: tuple[str, ...] = ()
    disease_aliases: tuple[str, ...] = ()
    population: str = ""
    intervention_class: str = ""
    date_from: str = ""
    date_to: str = ""
    decision_question: str = ""
    output_language: str = ""

    def __post_init__(self) -> None:
        target = self.target.strip()
        disease = self.disease.strip()
        if not target:
            raise ValueError("target is required")
        if not disease:
            raise ValueError("disease is required")
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "disease", disease)
        object.__setattr__(self, "target_aliases", _strings(self.target_aliases))
        object.__setattr__(self, "disease_aliases", _strings(self.disease_aliases))
        for name in (
            "population",
            "intervention_class",
            "date_from",
            "date_to",
            "decision_question",
            "output_language",
        ):
            object.__setattr__(self, name, _text(getattr(self, name)))
        parsed_dates: dict[str, date] = {}
        for name in ("date_from", "date_to"):
            value = getattr(self, name)
            if not value:
                continue
            try:
                parsed_dates[name] = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name} must use YYYY-MM-DD") from exc
        if (
            "date_from" in parsed_dates
            and "date_to" in parsed_dates
            and parsed_dates["date_from"] > parsed_dates["date_to"]
        ):
            raise ValueError("date_from cannot be after date_to")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_aliases"] = list(self.target_aliases)
        payload["disease_aliases"] = list(self.disease_aliases)
        return payload


@dataclass(frozen=True)
class EvidenceRecord:
    schema_version: int
    record_id: str
    source_type: str
    source_id: str
    canonical_url: str
    retrieved_at: str
    query_id: str
    title: str
    target_submitted: str
    disease_submitted: str
    target_canonical: str = ""
    disease_canonical: str = ""
    target_aliases: tuple[str, ...] = ()
    disease_aliases: tuple[str, ...] = ()
    scope_population: str = ""
    date: str | None = None
    status: str | None = None
    evidence_class: str = "literature"
    study_design: str | None = None
    population_or_model: str | None = None
    intervention_or_exposure: str | None = None
    comparator: str | None = None
    endpoint: str | None = None
    sample_size: int | None = None
    follow_up: str | None = None
    registry_last_update: str | None = None
    data_cutoff: str | None = None
    result_direction: str | None = None
    source_locator: str = ""
    raw_artifact: str = ""
    identifiers: Mapping[str, str] = field(default_factory=dict)
    has_results: bool | None = None
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_aliases"] = list(self.target_aliases)
        payload["disease_aliases"] = list(self.disease_aliases)
        payload["identifiers"] = dict(self.identifiers)
        payload["limitations"] = list(self.limitations)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRecord":
        values = dict(payload)
        values["target_aliases"] = tuple(_strings(values.get("target_aliases")))
        values["disease_aliases"] = tuple(_strings(values.get("disease_aliases")))
        values["limitations"] = tuple(_strings(values.get("limitations")))
        values["identifiers"] = dict(_mapping(values.get("identifiers")))
        return cls(**values)


def normalize_pubmed(
    payload: Mapping[str, Any],
    *,
    scope: MedicalScope,
    query_id: str,
    retrieved_at: str,
) -> tuple[EvidenceRecord, ...]:
    result = _mapping(payload.get("result"))
    raw_uids = _sequence(result.get("uids"))
    if not raw_uids:
        raw_uids = tuple(key for key in result if key != "uids")
    rows: list[EvidenceRecord] = []
    seen: set[str] = set()
    for raw_uid in raw_uids:
        uid = _text(raw_uid)
        if not uid or uid in seen:
            continue
        entry = _mapping(result.get(uid))
        source_id = _text(entry.get("uid")) or uid
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        identifiers: dict[str, str] = {}
        for raw_identifier in _sequence(entry.get("articleids")):
            identifier = _mapping(raw_identifier)
            id_type = _text(identifier.get("idtype"))
            value = _text(identifier.get("value"))
            if id_type and value and id_type not in identifiers:
                identifiers[id_type] = value
        rows.append(
            EvidenceRecord(
                schema_version=1,
                record_id=f"pubmed:{source_id}",
                source_type="pubmed",
                source_id=source_id,
                canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{source_id}/",
                retrieved_at=retrieved_at,
                query_id=query_id,
                title=_text(entry.get("title")),
                target_submitted=scope.target,
                disease_submitted=scope.disease,
                target_aliases=scope.target_aliases,
                disease_aliases=scope.disease_aliases,
                scope_population=scope.population,
                date=_text(entry.get("pubdate")) or None,
                evidence_class="literature",
                source_locator=f"result.{source_id}",
                identifiers=identifiers,
                limitations=("PubMed summary metadata; full text not reviewed.",),
            )
        )
    return tuple(rows)


def normalize_clinical_trials(
    payload: Mapping[str, Any],
    *,
    scope: MedicalScope,
    query_id: str,
    retrieved_at: str,
) -> tuple[EvidenceRecord, ...]:
    rows: list[EvidenceRecord] = []
    seen: set[str] = set()
    for index, raw_study in enumerate(_sequence(payload.get("studies"))):
        study = _mapping(raw_study)
        protocol = _mapping(study.get("protocolSection"))
        identification = _mapping(protocol.get("identificationModule"))
        source_id = _text(identification.get("nctId"))
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        status_module = _mapping(protocol.get("statusModule"))
        design = _mapping(protocol.get("designModule"))
        phases = _strings(design.get("phases"))
        design_parts = tuple(
            value
            for value in (_text(design.get("studyType")), *phases)
            if value
        )
        enrollment = _mapping(design.get("enrollmentInfo"))
        raw_count = enrollment.get("count")
        sample_size = (
            int(raw_count)
            if isinstance(raw_count, (int, float)) and not isinstance(raw_count, bool)
            else None
        )
        arms = _mapping(protocol.get("armsInterventionsModule"))
        intervention_names = [
            _text(_mapping(item).get("name"))
            for item in _sequence(arms.get("interventions"))
        ]
        comparator_names = [
            _text(group.get("label"))
            for raw_group in _sequence(arms.get("armGroups"))
            if (
                (group := _mapping(raw_group))
                and _text(group.get("type"))
                in {"ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "SHAM_COMPARATOR"}
            )
        ]
        outcomes = _mapping(protocol.get("outcomesModule"))
        primary_outcomes = [
            _mapping(item) for item in _sequence(outcomes.get("primaryOutcomes"))
        ]
        endpoint = _join([item.get("measure") for item in primary_outcomes])
        follow_up = _join([item.get("timeFrame") for item in primary_outcomes])
        eligibility = _mapping(protocol.get("eligibilityModule"))
        eligibility_parts = [
            _text(eligibility.get("sex")),
            _text(eligibility.get("minimumAge")),
            _text(eligibility.get("maximumAge")),
        ]
        population = _join(eligibility_parts)
        has_results = bool(study.get("hasResults") or study.get("resultsSection"))
        limitations = ["ClinicalTrials.gov registry metadata; publication not reviewed."]
        if not has_results:
            limitations.append("Registration record has no posted results.")
        rows.append(
            EvidenceRecord(
                schema_version=1,
                record_id=f"clinical_trials:{source_id}",
                source_type="clinical_trials",
                source_id=source_id,
                canonical_url=f"https://clinicaltrials.gov/study/{source_id}",
                retrieved_at=retrieved_at,
                query_id=query_id,
                title=_text(identification.get("briefTitle")),
                target_submitted=scope.target,
                disease_submitted=scope.disease,
                target_aliases=scope.target_aliases,
                disease_aliases=scope.disease_aliases,
                scope_population=scope.population,
                date=_text(_mapping(status_module.get("startDateStruct")).get("date"))
                or None,
                status=_text(status_module.get("overallStatus")) or None,
                evidence_class="clinical",
                study_design="; ".join(design_parts) if design_parts else None,
                population_or_model=population,
                intervention_or_exposure=_join(intervention_names),
                comparator=_join(comparator_names),
                endpoint=endpoint,
                sample_size=sample_size,
                follow_up=follow_up,
                registry_last_update=(
                    _text(status_module.get("lastUpdateSubmitDate")) or None
                ),
                data_cutoff=None,
                result_direction=None,
                source_locator=f"studies[{index}].protocolSection",
                identifiers={"nct": source_id},
                has_results=has_results,
                limitations=tuple(limitations),
            )
        )
    return tuple(rows)


def validate_evidence_record(record: EvidenceRecord) -> tuple[str, ...]:
    issues: list[str] = []
    if record.schema_version != 1:
        issues.append("schema_version must be 1")
    for name in (
        "record_id",
        "source_type",
        "source_id",
        "canonical_url",
        "retrieved_at",
        "query_id",
        "title",
        "target_submitted",
        "disease_submitted",
    ):
        if not _text(getattr(record, name)):
            issues.append(f"{name} is required")
    expected_id = f"{record.source_type}:{record.source_id}"
    if record.record_id and record.record_id != expected_id:
        issues.append(f"record_id must be {expected_id}")
    if record.canonical_url and not record.canonical_url.startswith("https://"):
        issues.append("canonical_url must use https")
    if record.sample_size is not None and record.sample_size < 0:
        issues.append("sample_size cannot be negative")
    if record.result_direction and record.has_results is False:
        issues.append("result_direction requires posted results")
    return tuple(issues)


# Connectors -----------------------------------------------------------------


_PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_CLINICAL_TRIALS_BASE = "https://clinicaltrials.gov/api/v2/studies"
_USER_AGENT = "Argus/0.1 medical-evidence-research"


@dataclass(frozen=True)
class RetrievalFailure:
    source_type: str
    query_id: str
    url: str
    retrieved_at: str
    error_type: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class RetrievalBatch:
    source_type: str
    query_id: str
    query_urls: tuple[str, ...]
    raw_payloads: tuple[Mapping[str, Any], ...]
    evidence: tuple[EvidenceRecord, ...]
    failures: tuple[RetrievalFailure, ...]


def medical_query_id(source_type: str, scope: MedicalScope) -> str:
    values = (source_type, scope.target, scope.disease)
    parts = [re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") for value in values]
    return "-".join(part for part in parts if part)


def _pubmed_clause(value: str, aliases: tuple[str, ...]) -> str:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in (value, *aliases):
        term = raw.strip().replace('"', "")
        folded = term.casefold()
        if term and folded not in seen:
            seen.add(folded)
            terms.append(f'"{term}"[Title/Abstract]')
    return "(" + " OR ".join(terms) + ")"


def build_pubmed_search_url(scope: MedicalScope, *, retmax: int = 100) -> str:
    term = " AND ".join(
        (
            _pubmed_clause(scope.target, scope.target_aliases),
            _pubmed_clause(scope.disease, scope.disease_aliases),
        )
    )
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": max(1, min(int(retmax), 10_000)),
        "term": term,
    }
    if scope.date_from or scope.date_to:
        params["datetype"] = "pdat"
        if scope.date_from:
            params["mindate"] = scope.date_from.replace("-", "/")
        if scope.date_to:
            params["maxdate"] = scope.date_to.replace("-", "/")
    return f"{_PUBMED_BASE}/esearch.fcgi?{urlencode(params)}"


def _build_pubmed_summary_url(source_ids: tuple[str, ...]) -> str:
    params = {
        "db": "pubmed",
        "retmode": "json",
        "id": ",".join(source_ids),
    }
    return f"{_PUBMED_BASE}/esummary.fcgi?{urlencode(params)}"


def build_clinical_trials_url(scope: MedicalScope, *, page_size: int = 100) -> str:
    params = {
        "format": "json",
        "countTotal": "true",
        "pageSize": max(1, min(int(page_size), 1_000)),
        "query.cond": scope.disease,
        "query.intr": scope.target,
    }
    if scope.date_from or scope.date_to:
        lower = scope.date_from or "MIN"
        upper = scope.date_to or "MAX"
        params["filter.advanced"] = (
            f"AREA[StudyFirstPostDate]RANGE[{lower},{upper}]"
        )
    return f"{_CLINICAL_TRIALS_BASE}?{urlencode(params)}"


def _default_open(request: Request, timeout: float):
    return urlopen(request, timeout=timeout)


def _fetch_json(
    url: str,
    *,
    opener: Callable[..., Any],
    timeout: float,
) -> Mapping[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": _USER_AGENT})
    with opener(request, timeout) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("source response is not a JSON object")
    return payload


def _retrieval_failure(
    source_type: str,
    query_id: str,
    url: str,
    retrieved_at: str,
    exc: BaseException,
) -> RetrievalFailure:
    if isinstance(exc, HTTPError):
        error_type = "http"
        retryable = exc.code == 429 or exc.code >= 500
    elif isinstance(exc, (TimeoutError, URLError, OSError)):
        error_type = "transport"
        retryable = True
    elif isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ValueError)):
        error_type = "parse"
        retryable = False
    else:
        error_type = "unexpected"
        retryable = False
    return RetrievalFailure(
        source_type=source_type,
        query_id=query_id,
        url=url,
        retrieved_at=retrieved_at,
        error_type=error_type,
        message=f"{type(exc).__name__}: {exc}"[:1_000],
        retryable=retryable,
    )


def fetch_pubmed(
    scope: MedicalScope,
    *,
    opener: Callable[..., Any] | None = None,
    retrieved_at: str | None = None,
    retmax: int = 100,
    timeout: float = 30.0,
) -> RetrievalBatch:
    timestamp = retrieved_at or _utc_now()
    query_id = medical_query_id("pubmed", scope)
    search_url = build_pubmed_search_url(scope, retmax=retmax)
    open_request = opener or _default_open
    try:
        search_payload = _fetch_json(
            search_url,
            opener=open_request,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - classified below
        return RetrievalBatch(
            source_type="pubmed",
            query_id=query_id,
            query_urls=(search_url,),
            raw_payloads=(),
            evidence=(),
            failures=(
                _retrieval_failure("pubmed", query_id, search_url, timestamp, exc),
            ),
        )
    search_result = search_payload.get("esearchresult")
    raw_ids = search_result.get("idlist", ()) if isinstance(search_result, Mapping) else ()
    source_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids if isinstance(raw_ids, (list, tuple)) else ():
        source_id = str(raw_id or "").strip()
        if source_id and source_id not in seen:
            seen.add(source_id)
            source_ids.append(source_id)
    if not source_ids:
        return RetrievalBatch(
            source_type="pubmed",
            query_id=query_id,
            query_urls=(search_url,),
            raw_payloads=(search_payload,),
            evidence=(),
            failures=(),
        )
    summary_url = _build_pubmed_summary_url(tuple(source_ids))
    try:
        summary_payload = _fetch_json(
            summary_url,
            opener=open_request,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - classified below
        return RetrievalBatch(
            source_type="pubmed",
            query_id=query_id,
            query_urls=(search_url, summary_url),
            raw_payloads=(search_payload,),
            evidence=(),
            failures=(
                _retrieval_failure("pubmed", query_id, summary_url, timestamp, exc),
            ),
        )
    return RetrievalBatch(
        source_type="pubmed",
        query_id=query_id,
        query_urls=(search_url, summary_url),
        raw_payloads=(search_payload, summary_payload),
        evidence=normalize_pubmed(
            summary_payload,
            scope=scope,
            query_id=query_id,
            retrieved_at=timestamp,
        ),
        failures=(),
    )


def fetch_clinical_trials(
    scope: MedicalScope,
    *,
    opener: Callable[..., Any] | None = None,
    retrieved_at: str | None = None,
    page_size: int = 100,
    timeout: float = 30.0,
) -> RetrievalBatch:
    timestamp = retrieved_at or _utc_now()
    query_id = medical_query_id("clinical-trials", scope)
    url = build_clinical_trials_url(scope, page_size=page_size)
    open_request = opener or _default_open
    try:
        payload = _fetch_json(url, opener=open_request, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - classified below
        return RetrievalBatch(
            source_type="clinical_trials",
            query_id=query_id,
            query_urls=(url,),
            raw_payloads=(),
            evidence=(),
            failures=(
                _retrieval_failure(
                    "clinical_trials", query_id, url, timestamp, exc
                ),
            ),
        )
    return RetrievalBatch(
        source_type="clinical_trials",
        query_id=query_id,
        query_urls=(url,),
        raw_payloads=(payload,),
        evidence=normalize_clinical_trials(
            payload,
            scope=scope,
            query_id=query_id,
            retrieved_at=timestamp,
        ),
        failures=(),
    )


# Dossier --------------------------------------------------------------------


_REQUIRED_FILES = (
    "scope.json",
    "queries.jsonl",
    "evidence.jsonl",
    "evidence_matrix.csv",
    "target_disease_memo.md",
    "review.json",
)
_MATRIX_FIELDS = (
    "source_type",
    "source_id",
    "title",
    "date",
    "status",
    "evidence_class",
    "study_design",
    "population_or_model",
    "intervention_or_exposure",
    "comparator",
    "endpoint",
    "sample_size",
    "follow_up",
    "scope_population",
    "registry_last_update",
    "data_cutoff",
    "result_direction",
    "canonical_url",
    "raw_artifact",
    "limitations",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} line {line_number} is not an object")
        rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    text = "".join(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    _atomic_write(path, text)


def _append_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    existing = _read_jsonl(path)
    _write_jsonl(path, (*existing, *(dict(row) for row in rows)))


def _scope_matches(existing: Mapping[str, Any], scope: MedicalScope) -> bool:
    expected = scope.to_dict()
    for field, expected_value in expected.items():
        existing_value = existing.get(field)
        if field in {"target", "disease"}:
            if str(existing_value or "").strip().casefold() != str(
                expected_value
            ).casefold():
                return False
            continue
        if field in {"target_aliases", "disease_aliases"}:
            existing_aliases = tuple(
                str(value).strip().casefold()
                for value in (existing_value or ())
                if str(value).strip()
            )
            expected_aliases = tuple(
                str(value).strip().casefold()
                for value in expected_value
                if str(value).strip()
            )
            if existing_aliases != expected_aliases:
                return False
            continue
        if str(existing_value or "").strip() != str(expected_value or "").strip():
            return False
    return True


def _fixture_batch(
    source_type: str,
    payload: Mapping[str, Any],
    *,
    scope: MedicalScope,
    retrieved_at: str,
) -> RetrievalBatch:
    query_id = medical_query_id(source_type.replace("_", "-"), scope)
    if source_type == "pubmed":
        evidence = normalize_pubmed(
            payload,
            scope=scope,
            query_id=query_id,
            retrieved_at=retrieved_at,
        )
    else:
        evidence = normalize_clinical_trials(
            payload,
            scope=scope,
            query_id=query_id,
            retrieved_at=retrieved_at,
        )
    return RetrievalBatch(
        source_type=source_type,
        query_id=query_id,
        query_urls=(f"fixture://{source_type}",),
        raw_payloads=(payload,),
        evidence=evidence,
        failures=(),
    )


def _raw_path(directory: Path, query_id: str, retrieved_at: str, index: int) -> Path:
    stamp = re.sub(r"[^0-9A-Za-z]+", "-", retrieved_at).strip("-") or "retrieval"
    stem = f"{stamp}-{query_id}-{index + 1}"
    candidate = directory / f"{stem}.json"
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{suffix}.json"
        suffix += 1
    return candidate


def _query_row(
    batch: RetrievalBatch,
    retrieved_at: str,
    raw_artifacts: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_type": batch.source_type,
        "query_id": batch.query_id,
        "query_urls": list(batch.query_urls),
        "retrieved_at": retrieved_at,
        "raw_payload_count": len(batch.raw_payloads),
        "raw_artifacts": list(raw_artifacts),
        "evidence_count": len(batch.evidence),
        "infrastructure_failure_count": len(batch.failures),
    }


def _write_matrix(path: Path, records: Sequence[EvidenceRecord]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_MATRIX_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = record.to_dict()
        row["limitations"] = " | ".join(record.limitations)
        writer.writerow(row)
    _atomic_write(path, buffer.getvalue())


def _render_memo(
    scope: MedicalScope,
    records: Sequence[EvidenceRecord],
    failure_count: int,
) -> str:
    counts = Counter(record.source_type for record in records)
    lines = [
        "# Target-Disease Research Memo",
        "",
        "**Status:** Pending independent Argus review",
        "",
        (
            "This dossier supports research and portfolio decisions; it is not "
            "diagnosis or treatment advice."
        ),
        "",
        "## Scope",
        "",
        f"- Target: {scope.target}",
        f"- Disease: {scope.disease}",
        f"- Population: {scope.population or 'Not specified'}",
        f"- Decision question: {scope.decision_question or 'Not specified'}",
        "",
        "## Evidence Inventory",
        "",
        f"- PubMed records: {counts.get('pubmed', 0)}",
        f"- ClinicalTrials.gov records: {counts.get('clinical_trials', 0)}",
        f"- Infrastructure failures: {failure_count}",
        "",
        "| Source | ID | Title | Status | URL |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        title = record.title.replace("|", "\\|")
        lines.append(
            f"| {record.source_type} | {record.source_id} | {title} | "
            f"{record.status or ''} | {record.canonical_url} |"
        )
    if not records:
        lines.append("| - | - | No usable evidence records retrieved | - | - |")
    lines.extend(
        (
            "",
            "## Interpretation Boundary",
            "",
            "This deterministic memo is an evidence inventory, not a biomedical "
            "conclusion. PubMed summaries are metadata rather than verified full text, "
            "and trial registration does not establish efficacy. Mechanism, safety, "
            "comparability, conflicts, and claim wording require independent review.",
            "",
        )
    )
    return "\n".join(lines)


def build_target_disease_dossier(
    project_root: Path | str,
    *,
    target: str,
    disease: str,
    target_aliases: Sequence[str] = (),
    disease_aliases: Sequence[str] = (),
    population: str = "",
    intervention_class: str = "",
    date_from: str = "",
    date_to: str = "",
    decision_question: str = "",
    output_language: str = "",
    pubmed_payload: Mapping[str, Any] | None = None,
    clinical_trials_payload: Mapping[str, Any] | None = None,
    retrieved_at: str | None = None,
    live: bool = False,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser()
    if not root.is_dir():
        raise ValueError(f"project_root is not an existing directory: {root}")
    scope = MedicalScope(
        target=target,
        disease=disease,
        target_aliases=tuple(target_aliases),
        disease_aliases=tuple(disease_aliases),
        population=population,
        intervention_class=intervention_class,
        date_from=date_from,
        date_to=date_to,
        decision_question=decision_question,
        output_language=output_language,
    )
    timestamp = retrieved_at or _utc_now()
    medical = root / "medical"
    medical.mkdir(parents=True, exist_ok=True)
    scope_path = medical / "scope.json"
    if scope_path.is_file():
        existing_scope = json.loads(scope_path.read_text(encoding="utf-8"))
        if not isinstance(existing_scope, Mapping) or not _scope_matches(
            existing_scope, scope
        ):
            raise ValueError(
                "existing medical scope differs from the requested scope; "
                "use a separate Argus project"
            )
    scope_payload = {"schema_version": 1, **scope.to_dict()}
    _atomic_write(scope_path, _json_text(scope_payload))

    batches: list[RetrievalBatch] = []
    if pubmed_payload is not None:
        batches.append(
            _fixture_batch(
                "pubmed", pubmed_payload, scope=scope, retrieved_at=timestamp
            )
        )
    elif live:
        batches.append(
            fetch_pubmed(scope, opener=opener, retrieved_at=timestamp)
        )
    if clinical_trials_payload is not None:
        batches.append(
            _fixture_batch(
                "clinical_trials",
                clinical_trials_payload,
                scope=scope,
                retrieved_at=timestamp,
            )
        )
    elif live:
        batches.append(
            fetch_clinical_trials(scope, opener=opener, retrieved_at=timestamp)
        )

    query_rows: list[dict[str, Any]] = []
    new_records: list[EvidenceRecord] = []
    failure_rows: list[dict[str, Any]] = []
    for batch in batches:
        failure_rows.extend(asdict(failure) for failure in batch.failures)
        raw_dir = medical / "raw" / batch.source_type
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_artifacts: list[str] = []
        for index, payload in enumerate(batch.raw_payloads):
            raw_path = _raw_path(raw_dir, batch.query_id, timestamp, index)
            _atomic_write(
                raw_path,
                _json_text(dict(payload)),
            )
            raw_artifacts.append(raw_path.relative_to(root).as_posix())
        query_rows.append(_query_row(batch, timestamp, raw_artifacts))
        evidence_raw = raw_artifacts[-1] if raw_artifacts else ""
        new_records.extend(
            replace(record, raw_artifact=evidence_raw) for record in batch.evidence
        )

    _append_jsonl(medical / "queries.jsonl", query_rows)
    failure_path = medical / "infrastructure_failures.jsonl"
    if failure_rows:
        _append_jsonl(failure_path, failure_rows)
    all_failure_rows = _read_jsonl(failure_path)
    _append_jsonl(
        medical / "evidence_history.jsonl",
        [record.to_dict() for record in new_records],
    )

    current_path = medical / "evidence.jsonl"
    current_records: dict[str, EvidenceRecord] = {}
    for payload in _read_jsonl(current_path):
        record = EvidenceRecord.from_dict(payload)
        current_records[record.record_id] = record
    for record in new_records:
        current_records[record.record_id] = record
    records = tuple(current_records.values())
    _write_jsonl(current_path, [record.to_dict() for record in records])
    _write_matrix(medical / "evidence_matrix.csv", records)

    review_path = medical / "review.json"
    if review_path.is_file():
        prior_review = json.loads(review_path.read_text(encoding="utf-8"))
        if isinstance(prior_review, Mapping):
            _append_jsonl(
                medical / "review_history.jsonl",
                [{**dict(prior_review), "superseded_at": timestamp}],
            )
    review = {"schema_version": 1, "status": "pending_review", "certified": False}
    _atomic_write(review_path, _json_text(review))
    _atomic_write(
        medical / "target_disease_memo.md",
        _render_memo(scope, records, len(all_failure_rows)),
    )

    usable_source_count = sum(
        1 for batch in batches if batch.raw_payloads and not batch.failures
    )
    return {
        "project_root": str(root.resolve()),
        "medical_root": str(medical.resolve()),
        "evidence_count": len(records),
        "new_evidence_count": len(new_records),
        "usable_source_count": usable_source_count,
        "new_infrastructure_failure_count": len(failure_rows),
        "infrastructure_failure_count": len(all_failure_rows),
        "review_status": "pending_review",
    }


def _project_artifact_status(root: Path, raw_path: str) -> str:
    text = str(raw_path or "").strip()
    relative = Path(text)
    if not text or relative.is_absolute() or ".." in relative.parts:
        return "outside"
    try:
        resolved = (root / relative).resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return "outside"
    return "ok" if resolved.is_file() else "missing"


def validate_dossier(project_root: Path | str) -> tuple[str, ...]:
    root = Path(project_root).expanduser().resolve()
    medical = root / "medical"
    issues: list[str] = []
    for name in _REQUIRED_FILES:
        if not (medical / name).is_file():
            issues.append(f"missing {name}")

    scope_path = medical / "scope.json"
    if scope_path.is_file():
        try:
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            if not isinstance(scope, dict):
                issues.append("scope.json is not a JSON object")
            else:
                for field in ("target", "disease"):
                    if not str(scope.get(field) or "").strip():
                        issues.append(f"scope.json missing {field}")
        except json.JSONDecodeError:
            issues.append("scope.json is not valid JSON")

    records: list[EvidenceRecord] = []
    evidence_path = medical / "evidence.jsonl"
    if evidence_path.is_file():
        try:
            payloads = _read_jsonl(evidence_path)
            if not payloads:
                issues.append("evidence.jsonl contains no records")
            for index, payload in enumerate(payloads, start=1):
                try:
                    record = EvidenceRecord.from_dict(payload)
                except (TypeError, ValueError) as exc:
                    issues.append(f"evidence.jsonl line {index} is invalid: {exc}")
                    continue
                records.append(record)
                issues.extend(
                    f"evidence.jsonl line {index}: {issue}"
                    for issue in validate_evidence_record(record)
                )
                raw_artifact = str(record.raw_artifact or "").strip()
                if not raw_artifact:
                    issues.append(
                        f"evidence.jsonl line {index}: raw_artifact is required"
                    )
                elif _project_artifact_status(root, raw_artifact) == "outside":
                    issues.append(
                        f"evidence.jsonl line {index}: raw_artifact is outside project"
                    )
                elif _project_artifact_status(root, raw_artifact) == "missing":
                    issues.append(
                        f"evidence.jsonl line {index}: raw_artifact does not exist"
                    )
        except ValueError as exc:
            issues.append(f"evidence.jsonl is invalid: {exc}")

    matrix_path = medical / "evidence_matrix.csv"
    if matrix_path.is_file():
        try:
            with matrix_path.open(encoding="utf-8", newline="") as handle:
                matrix_rows = list(csv.DictReader(handle))
            if records and len(matrix_rows) != len(records):
                issues.append("evidence_matrix.csv row count does not match evidence.jsonl")
        except (OSError, csv.Error) as exc:
            issues.append(f"evidence_matrix.csv is invalid: {exc}")

    memo_path = medical / "target_disease_memo.md"
    if memo_path.is_file():
        memo = " ".join(memo_path.read_text(encoding="utf-8").casefold().split())
        if "not diagnosis or treatment advice" not in memo:
            issues.append("target_disease_memo.md missing non-diagnostic boundary")

    review_path = medical / "review.json"
    if review_path.is_file():
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
            if not isinstance(review, dict):
                issues.append("review.json is not a JSON object")
            elif not isinstance(review.get("certified"), bool):
                issues.append("review.json certified must be boolean")
        except json.JSONDecodeError:
            issues.append("review.json is not valid JSON")

    queries_path = medical / "queries.jsonl"
    if queries_path.is_file():
        try:
            query_rows = _read_jsonl(queries_path)
            if not query_rows:
                issues.append("queries.jsonl contains no records")
            for index, row in enumerate(query_rows, start=1):
                raw_artifacts = row.get("raw_artifacts")
                if not isinstance(raw_artifacts, list):
                    issues.append(
                        f"queries.jsonl line {index}: raw_artifacts must be a list"
                    )
                    continue
                for raw in raw_artifacts:
                    raw_status = _project_artifact_status(root, str(raw or ""))
                    if raw_status == "outside":
                        issues.append(
                            f"queries.jsonl line {index}: raw_artifacts entry is outside project"
                        )
                    elif raw_status == "missing":
                        issues.append(
                            f"queries.jsonl line {index}: raw_artifacts entry does not exist"
                        )
        except ValueError as exc:
            issues.append(f"queries.jsonl is invalid: {exc}")
    return tuple(issues)


def load_optional_json(path: str) -> Mapping[str, Any] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"fixture is not a JSON object: {path}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a target-disease dossier whose every claim traces to its source, "
        "or --check an existing one"
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate PROJECT_ROOT/medical/ instead of building; exit 1 lists each issue",
    )
    parser.add_argument("--target", default="")
    parser.add_argument("--disease", default="")
    parser.add_argument("--target-alias", action="append", default=[])
    parser.add_argument("--disease-alias", action="append", default=[])
    parser.add_argument("--population", default="")
    parser.add_argument("--intervention-class", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--decision-question", default="")
    parser.add_argument("--output-language", default="")
    parser.add_argument("--pubmed-fixture", default="")
    parser.add_argument("--clinical-trials-fixture", default="")
    parser.add_argument("--retrieved-at", default="")
    parser.add_argument("--live", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check:
        issues = validate_dossier(args.project_root)
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        if not issues:
            print("medical dossier: structurally complete")
        return 1 if issues else 0
    if not args.target.strip() or not args.disease.strip():
        parser.error("--target and --disease are required to build a dossier")
    try:
        result = build_target_disease_dossier(
            args.project_root,
            target=args.target,
            disease=args.disease,
            target_aliases=args.target_alias,
            disease_aliases=args.disease_alias,
            population=args.population,
            intervention_class=args.intervention_class,
            date_from=args.date_from,
            date_to=args.date_to,
            decision_question=args.decision_question,
            output_language=args.output_language,
            pubmed_payload=load_optional_json(args.pubmed_fixture),
            clinical_trials_payload=load_optional_json(
                args.clinical_trials_fixture
            ),
            retrieved_at=args.retrieved_at or None,
            live=args.live,
        )
    except (OSError, ValueError) as exc:
        print(f"medical dossier failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["usable_source_count"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
