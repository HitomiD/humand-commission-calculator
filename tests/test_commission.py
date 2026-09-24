"""Tests for the commission calculation, with the hand-written rules."""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from calculator.commission import (
    build_lines, eligible_range, estado, months_already, tier_breakdown,
)
from calculator.data import DataIssue, load_inputs
from calculator.models import ApprovedPayment, CommissionRule, Payment, Tier, tier_issues
from calculator.payments import FetchResult, PaymentError
from calculator.reference_rules import reference_rule
from tests.test_input_models import _mock_payments

EXPECTED = Path(__file__).parent / "fixtures" / "expected_output_PUBLIC.csv"
COLUMNS = ["deal_id", "payment_id", "base_usada", "base_mensual", "meses_elegibles",
           "monto_a_comisionar", "estado", "memo"]


@pytest.fixture(scope="module")
def lines():
    fetched = FetchResult([Payment.model_validate(p) for p in _mock_payments()])
    return {l.payment_id: l for l in build_lines(load_inputs(), fetched, reference_rule)}


# --- Against the expected output -------------------------------------------

def test_matches_public_expected_output(lines):
    with open(EXPECTED, newline="", encoding="utf-8") as f:
        expected = list(csv.DictReader(f))
    assert len(expected) == 3
    for row in expected:
        line = lines[row["payment_id"]]
        for c in COLUMNS:
            got, want = getattr(line, c), row[c]
            if c in ("base_mensual", "monto_a_comisionar"):
                assert got == Decimal(want), (row["payment_id"], c)
            else:
                assert got == want, (row["payment_id"], c)


# The other new payments, worked out by hand in decisions.md (not confirmed
# by the public output).
@pytest.mark.parametrize("payment_id, meses, monto, est", [
    ("D02_p13", "m13-m13", "750", "en_curso"),
    ("D03_p01", "m1-m12", "0", "no_corresponde"),
    ("D07_p01", "m1-m12", "6000", "completo"),
    ("D08_p13", None, "0", "no_corresponde"),
])
def test_matches_hand_worked_reference(lines, payment_id, meses, monto, est):
    line = lines[payment_id]
    assert (line.meses_elegibles, line.monto_a_comisionar, line.estado) == (meses, Decimal(monto), est)


def test_one_line_per_new_payment(lines):
    assert sorted(lines) == ["D01_p06", "D02_p13", "D03_p01", "D04_p01",
                             "D05_p05", "D06_p09", "D07_p01", "D08_p13"]


def test_fee_is_pending(lines):
    line = lines["D04_p01"]
    assert line.estado == "requiere_revision" and "D-13" in line.reason
    assert line.monto_a_comisionar == 0


# --- Pieces ------------------------------------------------------------------

def test_months_already_sums_months_and_skips_blocked():
    rows = [ApprovedPayment(deal_id="D02", payment_id="a", meses_cubiertos=12),
            ApprovedPayment(deal_id="D01", payment_id="b", meses_cubiertos=1),
            ApprovedPayment(deal_id="D01", payment_id="c", meses_cubiertos=3)]
    assert months_already(rows, blocked={"D02"}) == {"D02": None, "D01": 4}


@pytest.mark.parametrize("already, covered, cap, expected", [
    (5, 1, 12, (6, 6)),
    (8, 6, 12, (9, 12)),     # cut at the cap (D-09)
    (12, 1, 12, None),       # nothing left
    (4, 12, None, (5, 16)),  # no limit
])
def test_eligible_range(already, covered, cap, expected):
    assert eligible_range(already, covered, cap) == expected


def test_tier_breakdown_splits_across_tiers():
    tiers = (Tier(from_month=1, to_month=12, pct=50), Tier(from_month=13, pct=30))
    slices = tier_breakdown(5, 16, tiers, Decimal(722))
    assert [(s.from_month, s.to_month, s.months) for s in slices] == [(5, 12, 8), (13, 16, 4)]
    assert sum(s.amount for s in slices) == Decimal("3754.4")


def test_estado():
    assert estado(None) == "en_curso"
    assert estado(0) == "completo"
    assert estado(6) == "incompleto"


def test_tier_issues():
    assert tier_issues((Tier(from_month=1, to_month=12, pct=50), Tier(from_month=13, pct=30))) == []
    assert tier_issues(()) == ["no tiers"]
    assert tier_issues((Tier(from_month=2, to_month=12, pct=50),)) != []
    assert tier_issues((Tier(from_month=1, to_month=12, pct=50), Tier(from_month=14, pct=30))) != []
    assert tier_issues((Tier(from_month=1, pct=50), Tier(from_month=13, pct=30))) != []


def test_max_months_comes_from_the_last_tier():
    def rule(*tiers):
        return CommissionRule(deal_id="X", tiers=tiers, on_total=False, source_hash="h")
    assert rule(Tier(from_month=1, to_month=24, pct=35)).max_months == 24
    assert rule(Tier(from_month=1, to_month=12, pct=50), Tier(from_month=13, pct=30)).max_months is None


# --- What goes to review --------------------------------------------------

def _payment(pid, deal="D01", term="mensual", amount=300):
    return Payment(deal_id=deal, payment_id=pid, payment_date="2026-06-01",
                   amount=amount, payment_term=term, currency="USD")


def test_blocked_unknown_and_broken_payments_go_to_review():
    inputs = load_inputs()
    inputs.issues.append(DataIssue("hubspot_deals.csv", 2, "D01", "bad"))
    fetched = FetchResult(
        [_payment("D01_p06"), _payment("D99_p01", deal="D99")],
        errors=[PaymentError("D02_x", "D02", "bad term")],
    )
    got = {l.payment_id: l for l in build_lines(inputs, fetched, reference_rule)}
    assert {l.estado for l in got.values()} == {"requiere_revision"}
    assert "data issues" in got["D01_p06"].reason
    assert "not found" in got["D99_p01"].reason
    assert "bad term" in got["D02_x"].reason


def test_later_payments_follow_the_running_total():
    # Two new monthly payments for D01 (5 months done): m6 then m7.
    fetched = FetchResult([_payment("D01_p06"), _payment("D01_p07")])
    got = {l.payment_id: l for l in build_lines(load_inputs(), fetched, reference_rule)}
    assert got["D01_p06"].meses_elegibles == "m6-m6"
    assert got["D01_p07"].meses_elegibles == "m7-m7"


def test_payment_after_a_review_line_is_held():
    # D04's first payment waits for the fee rule, so its next one can't be placed.
    fetched = FetchResult([_payment("D04_p01", "D04", "anual", 7200), _payment("D04_p02", "D04")])
    got = {l.payment_id: l for l in build_lines(load_inputs(), fetched, reference_rule)}
    assert got["D04_p02"].estado == "requiere_revision"
    assert "D04_p01" in got["D04_p02"].reason


def test_rule_with_issues_goes_to_review():
    def broken(deal):
        return reference_rule(deal).model_copy(update={"issues": ("tiers overlap",)})
    fetched = FetchResult([_payment("D01_p06")])
    [line] = build_lines(load_inputs(), fetched, broken)
    assert line.estado == "requiere_revision" and "tiers overlap" in line.reason
