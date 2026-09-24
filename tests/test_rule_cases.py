"""Offline checks of the evaluation set and its scoring (``tests/eval_rules.py``).

No LLM is called: this only makes sure the invented cases are well formed,
aren't copied from the prompt, and are scored as intended.
"""

import json

import pytest

from calculator.models import CommissionRule, Tier, tier_issues
from calculator.rules import INSTRUCTIONS
from tests.eval_rules import CASES_FILE, expected_rule, invented_cases, meaning, outcome, real_cases

RAW = json.loads(CASES_FILE.read_text())
KINDS = {"plano", "tramos", "perpetuo", "otro_idioma", "typo", "no_pagar", "base",
         "fee_completo", "fee_incompleto", "ambiguo", "por_pagos", "sin_duracion",
         "condicional", "contradiccion"}


def test_ids_are_unique_and_every_case_is_explained():
    assert len({c["id"] for c in RAW}) == len(RAW)
    for c in RAW:
        assert c["kind"] in KINDS and c["why"] and c.get("batch", 1) in (1, 2), c["id"]


@pytest.mark.parametrize("case", invented_cases(), ids=lambda c: c.id)
def test_expected_rules_are_valid(case):
    raw = next(c for c in RAW if c["id"] == case.id)
    if raw["expected"] != "revision":
        rule = expected_rule(raw["expected"], case.deal)  # raises on a bad tier or fee
        assert tier_issues(rule.tiers) == [], case.id


def test_no_case_is_one_of_the_prompts_examples():
    # Otherwise the evaluation would measure copying, not reading.
    for c in RAW:
        for text in (c["pct"], c.get("notes") or ""):
            assert not text or text not in INSTRUCTIONS, c["id"]


def test_every_kind_has_cases_that_must_go_to_review_or_be_paid():
    kinds_review = {c["kind"] for c in RAW if c["expected"] == "revision"}
    assert {"base", "fee_incompleto", "ambiguo"} <= kinds_review


def test_real_cases_follow_the_reference_rules():
    real = {c.id: c for c in real_cases()}
    assert len(real) == 8
    assert real["D04"].expected is None  # incomplete fee: must go to review
    assert real["D01"].expected is not None


def _rule(*tiers, issues=()):
    return CommissionRule(deal_id="X", tiers=tuple(Tier(from_month=a, to_month=b, pct=p) for a, b, p in tiers),
                          on_total=False, issues=issues, source_text="")


def test_meaning_merges_equivalent_tiers():
    assert meaning(_rule((1, 12, 50), (13, 24, 50))) == meaning(_rule((1, 24, 50)))
    assert meaning(_rule((1, 12, 50), (13, 24, 30))) != meaning(_rule((1, 24, 50)))


def test_outcome():
    expected = meaning(_rule((1, 12, 50)))
    assert outcome(expected, _rule((1, 12, 50))) == "ok"
    assert outcome(expected, _rule((1, 12, 50), issues=("x",))) == "flagged"
    assert outcome(expected, _rule((1, 24, 50))) == "WRONG"
    assert outcome(None, _rule((1, 12, 50), issues=("x",))) == "ok"
    assert outcome(None, _rule((1, 12, 50))) == "WRONG"  # paid when it should go to review
