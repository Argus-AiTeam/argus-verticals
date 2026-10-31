"""Standalone speedrun structural evidence check, adapted from Argus metric_evidence."""


from __future__ import annotations


import argparse
import csv
import math
import sys
from pathlib import Path


class EvidenceError(ValueError):
    """Raised when no trustworthy scored row is present."""


_SPEEDRUN_METRICS = {
    "val_bpb",
    "mean_val_bpb",
    "seconds_to_target",
    "wall_seconds",
    "score",
    "metric_value",
}


def _finite_number(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _csv_rows(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = {str(name or "").strip().lower() for name in (reader.fieldnames or [])}
            rows = [
                {str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()}
                for row in reader
            ]
    except (OSError, csv.Error) as exc:
        raise EvidenceError(f"{path}: unreadable CSV: {exc}") from exc
    return fields, rows


def _candidate_csvs(project_root: Path, pattern: str) -> list[Path]:
    root = project_root.resolve()
    paths: set[Path] = set()
    for rel in ("attempts", "experiments"):
        base = root / rel
        if base.is_dir():
            paths.update(
                path
                for path in base.rglob(pattern)
                if _is_contained_file(root, path)
            )
    return sorted(paths)


def _is_contained_file(project_root: Path, path: Path) -> bool:
    root = project_root.resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False
    return resolved.is_relative_to(root) and resolved.is_file()


def validate_speedrun_evidence(project_root: Path) -> Path:
    """Return a results CSV containing at least one finite metric value."""
    for path in _candidate_csvs(project_root, "results.csv"):
        fields, rows = _csv_rows(path)
        metric_fields = fields & _SPEEDRUN_METRICS
        if metric_fields and any(
            _finite_number(row.get(field)) is not None
            for row in rows
            for field in metric_fields
        ):
            return path
    raise EvidenceError(
        "no attempts/**/results.csv or experiments/**/results.csv contains a "
        f"finite metric column ({', '.join(sorted(_SPEEDRUN_METRICS))})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="speedrun-evidence")
    parser.add_argument("kind", choices=["speedrun"])
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        path = validate_speedrun_evidence(root)
    except EvidenceError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"OK: structured metric evidence in {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
