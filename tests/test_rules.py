"""Tests for validating what the LLM read into a rule (``calculator/rules.py``).

No LLM is called here: the extractions are written by hand, and Gemini is
replaced by a fake.
"""

from decimal import Decimal

import pytest

import calculator.rules
from calculator.data import load_inputs
from calculator.models import Deal, ExtractedFee, ExtractedTier, RuleExtraction
from calculator.reference_rules import reference_rule
from calculator.rules import read_rules, rule_text, to_rule


def _tier(from_month, to_month, pct):
    return ExtractedTier(from_month=from_month, to_month=to_month, pct=pct)


def _read(tiers, do_not_pay=False, fee=None, base=None, flags=()):
    return RuleExtraction(tiers=tiers, do_not_pay=do_not_pay, fee=fee,
                          base_mencionada=base, flags=list(flags))


_YEAR_1_THEN_30 = [_tier(1, 12, 50.0), _tier(13, None, 30.0)]

# What a perfect reading of each deal's text returns.
PERFECT = {
    "D01": _read([_tier(1, 12, 25.0)]),
    "D02": _read(_YEAR_1_THEN_30),
    "D03": _read([_tier(1, 24, 35.0)], do_not_pay=True, base="total"),
    "D04": _read(_YEAR_1_THEN_30, base="total",
                 fee=ExtractedFee(total=1500.0, mode="unspecified", value=None)),
    "D05": _read(_YEAR_1_THEN_30),
    "D06": _read([_tier(1, 12, 50.0)]),
    "D07": _read([_tier(1, 12, 50.0)]),
    "D08": _read([_tier(1, 12, 50.0)]),
}


@pytest.fixture(scope="module")
def deals() -> dict[str, Deal]:
    return {d.deal_id: d for d in load_inputs().deals}


def test_every_deal_has_a_perfect_reading(deals):
    assert set(PERFECT) == set(deals)


@pytest.mark.parametrize("deal_id", sorted(PERFECT))
def test_perfect_reading_gives_the_reference_rule(deals, deal_id):
    deal = deals[deal_id]
    assert to_rule(PERFECT[deal_id], deal) == reference_rule(deal)


def test_rule_keeps_the_labelled_text(deals):
    rule = to_rule(PERFECT["D02"], deals["D02"])
    assert rule.source_text == ("partner_commission_pct: 50% año 1 / 30% perpetuo\n"
                                "partner_commission_notes: ")
    assert rule.source_text == rule_text(deals["D02"])


def test_numbers_lose_float_noise(deals):
    rule = to_rule(_read([_tier(1, 12, 12.5), _tier(13, None, 30.0)]), deals["D02"])
    assert [str(t.pct) for t in rule.tiers] == ["12.5", "30"]


def test_base_comes_from_the_column_not_the_text(deals):
    assert to_rule(PERFECT["D01"], deals["D01"]).on_total is False
    assert to_rule(PERFECT["D02"], deals["D02"]).on_total is True


# Each bad reading, applied to D02 (commission_on_expansion = Yes).
BAD = {
    "no tiers": _read([]),
    "starts after m1": _read([_tier(2, 12, 50.0)]),
    "gap": _read([_tier(1, 12, 50.0), _tier(14, None, 30.0)]),
    "overlap": _read([_tier(1, 12, 50.0), _tier(12, None, 30.0)]),
    "open-ended tier not last": _read([_tier(1, None, 50.0), _tier(13, None, 30.0)]),
    "pct above 100": _read([_tier(1, 12, 150.0)]),
    "negative pct": _read([_tier(1, 12, -5.0)]),
    "ends before it starts": _read([_tier(1, 12, 50.0), _tier(13, 10, 30.0)]),
    "month 0": _read([_tier(0, 12, 50.0)]),
    "fixed fee without value": _read(_YEAR_1_THEN_30, fee=ExtractedFee(
        total=1500.0, mode="fixed_per_payment", value=None)),
    "unspecified fee with value": _read(_YEAR_1_THEN_30, fee=ExtractedFee(
        total=1500.0, mode="unspecified", value=100.0)),
    "fee of 0": _read(_YEAR_1_THEN_30, fee=ExtractedFee(total=0.0, mode="unspecified", value=None)),
    "fee pct above 100": _read(_YEAR_1_THEN_30, fee=ExtractedFee(
        total=1500.0, mode="pct_of_commission", value=120.0)),
    "base contradicts the column": _read(_YEAR_1_THEN_30, base="contrato"),
    "model flagged the text": _read(_YEAR_1_THEN_30, flags=["no queda claro si el 30% es perpetuo"]),
}


@pytest.mark.parametrize("case", sorted(BAD))
def test_bad_reading_becomes_an_issue(deals, case):
    rule = to_rule(BAD[case], deals["D02"])
    assert rule.issues, case


def test_base_mismatch_on_a_contract_deal(deals):
    rule = to_rule(_read([_tier(1, 12, 25.0)], base="total"), deals["D01"])
    assert rule.issues == ("el texto menciona la base 'total' pero commission_on_expansion es No",)


def test_invalid_tier_is_reported_once(deals):
    # A tier that fails validation shouldn't also produce gap/order issues from the rest.
    rule = to_rule(_read([_tier(1, 12, 150.0), _tier(13, None, 30.0)]), deals["D02"])
    assert rule.issues == ("tramo inválido: m1-m12 al 150.0%",)


def test_flags_are_kept_and_blank_ones_dropped(deals):
    rule = to_rule(_read(_YEAR_1_THEN_30, flags=["ambiguo", "  "]), deals["D02"])
    assert rule.issues == ("el modelo marcó: ambiguo",)


def test_fee_values_become_decimals(deals):
    rule = to_rule(_read(_YEAR_1_THEN_30, fee=ExtractedFee(
        total=1500.0, mode="fixed_per_payment", value=100.0)), deals["D02"])
    assert rule.issues == ()
    assert (rule.fee.total, rule.fee.value) == (Decimal(1500), Decimal(100))


# --- read_rules, with Gemini replaced by a fake ------------------------------

class _Gemini(list):
    """Calls made to the fake Gemini, as (text, model); ``fail_for`` holds texts that fail."""

    def __init__(self):
        super().__init__()
        self.fail_for: set[str] = set()


@pytest.fixture
def gemini(monkeypatch, deals):
    """A fake ``extract`` that returns the perfect reading of each deal."""
    by_text = {rule_text(d): PERFECT[d.deal_id] for d in deals.values()}
    calls = _Gemini()

    def extract(text, *, api_key, model):
        calls.append((text, model))
        if text in calls.fail_for:
            raise RuntimeError("503 unavailable")
        return by_text[text]
    monkeypatch.setattr(calculator.rules, "extract", extract)
    monkeypatch.setattr(calculator.rules, "_readings", {})
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    return calls


def test_read_rules_reads_every_deal(deals, gemini):
    result = read_rules(deals.values())
    assert result.model == "gemini-2.5-flash" and result.error is None
    assert result.rules == {k: reference_rule(d) for k, d in deals.items()}
    assert len(gemini) == 8


def test_readings_are_remembered_until_refresh(deals, gemini):
    read_rules(deals.values())
    read_rules(deals.values())
    assert len(gemini) == 8  # the second run used the remembered readings
    read_rules(deals.values(), refresh=True)
    assert len(gemini) == 16


def test_another_model_reads_again(deals, gemini, monkeypatch):
    read_rules(deals.values())
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    result = read_rules(deals.values())
    assert result.model == "gemini-2.5-pro"
    assert len(gemini) == 16 and gemini[-1][1] == "gemini-2.5-pro"


def test_a_failed_reading_is_an_issue_and_is_retried(deals, gemini):
    gemini.fail_for.add(rule_text(deals["D02"]))
    result = read_rules(deals.values())
    assert result.rules["D02"].issues == (
        "no se pudo leer la regla con gemini-2.5-flash: RuntimeError: 503 unavailable",)
    assert result.rules["D01"] == reference_rule(deals["D01"])  # the rest are read
    gemini.fail_for.clear()
    assert read_rules(deals.values()).rules["D02"] == reference_rule(deals["D02"])
    assert len(gemini) == 8 + 1  # only the failed one was asked again


def test_missing_key_sends_every_deal_to_review(deals, gemini, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    result = read_rules(deals.values())
    assert result.error == "GEMINI_API_KEY is not set"
    assert all(r.issues for r in result.rules.values())
    assert gemini == []


def test_readings_are_kept_for_the_page(deals, gemini):
    gemini.fail_for.add(rule_text(deals["D02"]))
    result = read_rules(deals.values())
    assert result.readings["D01"] == PERFECT["D01"]
    assert result.readings["D02"] is None  # not read: there is nothing to show


def test_describe_rule(deals):
    from calculator.rules import describe_rule
    assert describe_rule(reference_rule(deals["D02"])) == "m1-m12: 50%, m13-sin fin: 30%"
    assert describe_rule(reference_rule(deals["D03"])) == "m1-m24: 35%; no pagar"
    assert describe_rule(reference_rule(deals["D04"])) == "m1-m12: 50%, m13-sin fin: 30%; fee 1500 (unspecified)"
