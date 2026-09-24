"""Tests for grouping the lines into one transfer per partner (step 7)."""

from decimal import Decimal

import pytest

from calculator.commission import build_lines
from calculator.data import load_inputs
from calculator.models import CommissionLine, Payment
from calculator.payments import FetchResult
from calculator.pipeline import group_transfers, transfer_memo
from calculator.reference_rules import reference_rule
from tests.test_input_models import _mock_payments


@pytest.fixture(scope="module")
def transfers():
    fetched = FetchResult([Payment.model_validate(p) for p in _mock_payments()])
    lines = build_lines(load_inputs(), fetched, reference_rule)
    return {t.partner: t for t in group_transfers(lines)}


def test_one_transfer_per_partner_with_something_to_show(transfers):
    # Partner Este only has D03, which is no_corresponde: no transfer, nothing pending.
    assert list(transfers) == ["Partner Centro", "Partner Norte", "Partner Oeste", "Partner Sur"]


def test_transfer_sums_its_lines(transfers):
    sur = transfers["Partner Sur"]
    assert [l.payment_id for l in sur.lines] == ["D01_p06", "D06_p09"]
    assert sur.total == Decimal("1185.00")
    assert sur.memo == ("Partner Sur - 2 comisiones - total 1185.00: "
                        "Cliente Andes - comision pago m6-m6 - restan 6 | "
                        "Cliente Fohn - comision pago m9-m12 - restan 0")
    assert transfers["Partner Norte"].total == Decimal("4504.40")


def test_zero_lines_are_left_out(transfers):
    # D08_p13 is no_corresponde (cap already reached): not paid, not pending.
    centro = transfers["Partner Centro"]
    assert [l.payment_id for l in centro.lines] == ["D07_p01"] and centro.pending == ()


def test_lines_in_review_are_pending_not_paid(transfers):
    oeste = transfers["Partner Oeste"]
    assert oeste.lines == () and oeste.total == Decimal("0.00") and oeste.memo is None
    assert [l.payment_id for l in oeste.pending] == ["D04_p01"]


def test_lines_without_a_partner_belong_to_no_transfer():
    orphan = CommissionLine(deal_id="D99", payment_id="D99_p01", estado="requiere_revision",
                            reason="deal no encontrado")
    assert group_transfers([orphan]) == []


def test_single_line_memo():
    line = CommissionLine(deal_id="D01", payment_id="D01_p06", estado="incompleto", partner="P",
                          monto_a_comisionar=Decimal("63.00"), memo="Cliente Andes - comision pago m6-m6 - restan 6")
    assert transfer_memo("P", [line], Decimal("63.00")) == (
        "P - 1 comision - total 63.00: Cliente Andes - comision pago m6-m6 - restan 6")
