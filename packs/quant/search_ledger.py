"""Append-only search ledger for factor-mining trials, adapted from the Argus quant vertical.

Every backtest the agent runs — survivor *or* discard, success *or* failure —
is recorded here at the execution boundary (see backtest.py). The ledger is
the raw evidence the Reviewer reads to judge **search breadth** and
**multiple-testing / cherry-picking risk**: a factor with IC 0.05 found after
one hypothesis is very different from the same IC found after 3,000 silent
trials.

This is **evidence, not a gate**. The ledger does not decide pass/fail; the
reviewer interprets it. It is therefore deliberately dumb: it appends rows and
never edits or judges them.

Each JSONL row is ``{"index", "recorded_at", "payload"}``: a 0-based sequence
number, the write time, and the trial record. A deleted, reordered or inserted
row breaks the index sequence and is visible to ``verify``; an edited payload
is not, so the reviewer still compares cited rows against the trial outputs
they came from. Extra keys in older ledgers are ignored.

usage: python3 search_ledger.py verify [--path run/SEARCH_LEDGER.jsonl] [--json]
exit 0 when the rows are well-formed and in sequence, 1 when not (including a
missing file), 2 on bad usage.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LedgerRow:
    """One recorded trial: its position, write time, and the trial record."""

    index: int
    recorded_at: float
    payload: Mapping[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class SearchLedger:
    """An append-only JSONL ledger of factor-mining trials.

    Not thread-safe; one writer (the run-stage executor) is assumed. Reads are
    fail-open: a missing ledger is an empty ledger.
    """

    path: Path
    _count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        # Continue the sequence of an existing ledger rather than restarting it.
        last = None
        for last in self._iter_rows():
            pass
        if last is not None:
            self._count = last.index + 1

    def append(self, payload: Mapping[str, Any]) -> LedgerRow:
        """Append one trial record and return the written row.

        The payload is recorded verbatim. Callers should include enough to
        reproduce/audit the trial: factor id(s), combination spec, weighting,
        window, params, metrics, oos/is flag, run_id, status.
        """
        row = LedgerRow(index=self._count, recorded_at=time.time(), payload=dict(payload))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(row.to_json() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._count = row.index + 1
        return row

    def _iter_rows(self) -> Iterator[LedgerRow]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if not isinstance(data.get("payload"), Mapping):
                    raise TypeError("payload must be a JSON object")
                yield LedgerRow(
                    index=int(data["index"]),
                    recorded_at=float(data["recorded_at"]),
                    payload=data["payload"],
                )

    def rows(self) -> list[LedgerRow]:
        return list(self._iter_rows())

    def __len__(self) -> int:
        return self._count

    def gap(self) -> str | None:
        """The first row out of sequence, or ``None`` when indices run 0, 1, 2, ..."""
        for expected, row in enumerate(self._iter_rows()):
            if row.index != expected:
                return f"row {expected + 1} carries index {row.index}, expected {expected}"
        return None


def _cli(argv: list[str] | None = None) -> int:
    """Report whether a ledger is well-formed and in sequence, and how many trials it holds.

    A tool for the agent, not a gate over it: whether 3 trials is too few, or
    whether a gap is a crashed writer or a removed row, is the reviewer's call.
    """
    parser = argparse.ArgumentParser(
        prog="search_ledger.py",
        description="Check that a factor-mining search ledger is well-formed and in sequence.",
    )
    parser.add_argument("command", choices=["verify"])
    parser.add_argument(
        "--path",
        default="run/SEARCH_LEDGER.jsonl",
        help="ledger path (default: run/SEARCH_LEDGER.jsonl)",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    path = Path(args.path)
    report: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "valid": False, "rows": 0}
    if not path.is_file():
        detail = f"search-ledger: no ledger at {path}"
    else:
        # A hand-written or truncated file is what this tool exists to catch, so
        # it is reported, not raised.
        try:
            ledger = SearchLedger(path)
            report["rows"] = len(ledger.rows())
            gap = ledger.gap()
            report["valid"] = gap is None
            detail = (
                f"search-ledger: OK, {report['rows']} trial row(s) in {path}"
                if gap is None
                else f"search-ledger: OUT OF SEQUENCE in {path}: {gap} — "
                "a row was deleted, reordered or inserted after writing"
            )
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            detail = (
                f"search-ledger: NOT A LEDGER at {path} — rows are not "
                f"{{index, recorded_at, payload}} JSON objects ({exc!r})"
            )
    print(json.dumps(report, sort_keys=True) if args.json else detail)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
