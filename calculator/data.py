"""Loaders for the CSV inputs in ``data/`` (pipeline step 1).

A bad row never stops the run and is never dropped silently. It becomes a
``DataIssue`` tagged with its deal, and that deal is *blocked*: its new
payments are shown for human review instead of being calculated, while every
other deal is processed normally (decision D-22).

Only problems that make the whole file untrustworthy (missing file, wrong
header) raise ``DataError`` and stop the run.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from calculator.models import ApprovedPayment, Deal

# Resolved from this file, not the working directory, which differs between
# Uvicorn locally and the Vercel function.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEALS_FILE = "hubspot_deals.csv"
APPROVED_FILE = "pagos_aprobados.csv"

_Row = TypeVar("_Row", bound=BaseModel)


class DataError(Exception):
    """An input file cannot be used at all (missing, or wrong header)."""


@dataclass(frozen=True)
class DataIssue:
    """A problem with one row of an input file.

    ``deal_id`` is the raw value read from the row, when there is one. If
    ``blocks_deal`` is true, that deal's payments must not be calculated.
    """

    file: str
    row: int  # as an editor shows it: the header is row 1
    deal_id: str | None
    message: str
    blocks_deal: bool = True


@dataclass
class InputData:
    """Valid rows of both files, plus every problem found while loading."""

    deals: list[Deal]
    approved: list[ApprovedPayment]
    issues: list[DataIssue] = field(default_factory=list)

    @property
    def blocked_deals(self) -> set[str]:
        """Deals whose numbers cannot be trusted; their payments go to review."""
        return {i.deal_id for i in self.issues if i.blocks_deal and i.deal_id}


def _read(path: Path, model: type[_Row]) -> tuple[list[tuple[int, _Row]], list[DataIssue]]:
    """Parse each row into ``model``, collecting bad rows as issues.

    Returns the valid rows paired with their row numbers, and the issues.
    """
    if not path.is_file():
        raise DataError(f"{path.name}: file not found at {path}")
    rows, issues = [], []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(model.model_fields) - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"{path.name}: missing columns {sorted(missing)}")
        for line, raw in enumerate(reader, start=2):
            try:
                rows.append((line, model(**raw)))
            except ValidationError as e:
                problems = "; ".join(
                    f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()
                )
                deal_id = (raw.get("deal_id") or "").strip() or None
                issues.append(DataIssue(path.name, line, deal_id, problems))
    return rows, issues


def _duplicates(path: Path, rows: list[tuple[int, _Row]], key: str) -> tuple[set[str], list[DataIssue]]:
    """Find rows sharing ``key``; every copy is reported, since none can be trusted."""
    by_value: dict[str, list[tuple[int, _Row]]] = {}
    for line, row in rows:
        by_value.setdefault(getattr(row, key), []).append((line, row))
    dup_values = {v for v, group in by_value.items() if len(group) > 1}
    issues = [
        DataIssue(path.name, line, getattr(row, "deal_id"), f"duplicate {key} {value!r}")
        for value in sorted(dup_values)
        for line, row in by_value[value]
    ]
    return dup_values, issues


def load_inputs(data_dir: Path = DATA_DIR) -> InputData:
    """Load ``hubspot_deals.csv`` and ``pagos_aprobados.csv``.

    - Bad deal row, or duplicate ``deal_id``: the deal is blocked and left out.
    - Bad approved row, or duplicate ``payment_id``: the deal is blocked,
      because its months already commissioned are unknown.
    - Approved row for a deal not in the deals file: reported, blocks nothing.
    """
    deals_path, approved_path = data_dir / DEALS_FILE, data_dir / APPROVED_FILE

    deal_rows, issues = _read(deals_path, Deal)
    dup_deals, dup_issues = _duplicates(deals_path, deal_rows, "deal_id")
    issues += dup_issues
    deals = [d for _, d in deal_rows if d.deal_id not in dup_deals]

    approved_rows, approved_issues = _read(approved_path, ApprovedPayment)
    issues += approved_issues
    _, dup_issues = _duplicates(approved_path, approved_rows, "payment_id")
    issues += dup_issues

    # Checked against every deal_id seen in the file, valid or not, so a row
    # for a deal that is merely malformed isn't reported as unknown.
    known = {d.deal_id for _, d in deal_rows} | {i.deal_id for i in issues if i.file == DEALS_FILE}
    for line, a in approved_rows:
        if a.deal_id not in known:
            issues.append(DataIssue(
                approved_path.name, line, a.deal_id,
                f"unknown deal_id {a.deal_id!r}", blocks_deal=False,
            ))

    approved = [a for _, a in approved_rows]
    return InputData(deals=deals, approved=approved, issues=issues)
