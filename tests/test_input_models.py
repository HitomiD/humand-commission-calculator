"""Tests for the input models against the real data files and bad values."""

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from calculator.models import ApprovedPayment, Deal, Payment, PaymentTerm

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MOCK = ROOT / "mock-api" / "mock_stripe_endpoint.js"


def _rows(name: str) -> list[dict]:
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _mock_payments() -> list[dict]:
    # Read PAYMENTS straight from the supplied mock file, so the test always
    # checks the same data the endpoint serves. Requires Node.
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    script = (
        "const s=require('fs').readFileSync(process.argv[1],'utf8');"
        "console.log(JSON.stringify(eval(s.match(/const PAYMENTS = (\\[[\\s\\S]*?\\n\\]);/)[1])))"
    )
    out = subprocess.run(["node", "-e", script, str(MOCK)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.fixture
def deal_row() -> dict:
    return _rows("hubspot_deals.csv")[0]


@pytest.fixture
def payment_row() -> dict:
    return {
        "deal_id": "D01",
        "payment_id": "D01_m1",
        "payment_date": "2025-01-01",
        "amount": 252,
        "payment_term": "mensual",
        "currency": "USD",
    }


# --- Real data loads in full -------------------------------------------------

def test_all_deals_load():
    deals = [Deal(**r) for r in _rows("hubspot_deals.csv")]
    assert len(deals) == 8
    d04 = next(d for d in deals if d.deal_id == "D04")
    assert d04.commission_on_expansion is True
    assert d04.partner_commission_notes is None  # blank cell becomes None


def test_all_approved_payments_load():
    approved = [ApprovedPayment(**r) for r in _rows("pagos_aprobados.csv")]
    assert len(approved) == 30
    assert sum(a.meses_cubiertos for a in approved if a.deal_id == "D02") == 12


def test_all_mock_payments_load():
    payments = [Payment(**p) for p in _mock_payments()]
    assert len(payments) == 38
    assert len({p.payment_id for p in payments}) == 38


# --- Bad values are rejected --------------------------------------------------

@pytest.mark.parametrize("value", ["Si", "", "true", "1"])
def test_deal_rejects_unknown_expansion_value(deal_row, value):
    with pytest.raises(ValidationError):
        Deal(**{**deal_row, "commission_on_expansion": value})


@pytest.mark.parametrize("value", ["", "0", "-10"])
def test_deal_rejects_missing_or_non_positive_contract(deal_row, value):
    with pytest.raises(ValidationError):
        Deal(**{**deal_row, "amount_by_contract": value})


def test_deal_accepts_expansion_in_any_case(deal_row):
    assert Deal(**{**deal_row, "commission_on_expansion": "YES"}).commission_on_expansion is True


def test_approved_payment_rejects_zero_months():
    with pytest.raises(ValidationError):
        ApprovedPayment(deal_id="D01", payment_id="X", meses_cubiertos="0")


@pytest.mark.parametrize("field,value", [
    ("payment_term", "bimestral"),
    ("currency", "EUR"),
    ("amount", 0),
])
def test_payment_rejects_bad_values(payment_row, field, value):
    with pytest.raises(ValidationError):
        Payment(**{**payment_row, field: value})


# --- Payment terms --------------------------------------------------------------

@pytest.mark.parametrize("term,months", [
    ("mensual", 1), ("trimestral", 3), ("semestral", 6), ("anual", 12),
])
def test_payment_term_months(term, months):
    assert PaymentTerm(term).months == months
