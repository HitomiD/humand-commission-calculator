"""Evaluation of the real Gemini readings (``calculator/rules.py``).

Run on demand, not by pytest (it calls Gemini and needs GEMINI_API_KEY):

    python -m tests.eval_rules --runs 3              # real deals + invented cases
    python -m tests.eval_rules --set real --runs 1   # only the 8 deals in data/
    GEMINI_TEMPERATURE=0.5 python -m tests.eval_rules  # at another temperature

Two sets of cases:
- real: the deals in ``data/``, which must read as ``reference_rule``;
- invented: ``tests/fixtures/rule_cases.json``, texts written to test other
  phrasings, typos, fees and cases that must go to review. None of them is
  one of the prompt's examples (``tests/test_rule_cases.py`` checks it).
  Batch 2 was written after the last prompt change, so it measures the
  prompt on texts it wasn't adjusted to; results are also shown per batch.

Every run asks Gemini again. Each reading is:
- ok: the expected rule, or sent to review when review is expected;
- flagged: sent to review although a rule was expected (safe, but a miss);
- WRONG: a usable rule that isn't the expected one, or a usable rule when
  review was expected. A wrong amount would be paid.
A case is unstable when its readings differ between runs (D-37).
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from calculator.data import load_inputs
from calculator.models import CommissionRule, Deal, FeeDeduction, Tier
from calculator.reference_rules import reference_rule
from calculator.rules import describe_rule, read_rules

CASES_FILE = Path(__file__).parent / "fixtures" / "rule_cases.json"
REVIEW = "revisión"


@dataclass(frozen=True)
class Case:
    id: str
    kind: str
    batch: str  # "real", "1" or "2"
    deal: Deal
    expected: tuple | None  # meaning(), or None when the rule must go to review
    why: str


def meaning(rule: CommissionRule) -> tuple:
    """What a usable rule means for the calculation. Adjacent tiers with the
    same percentage are merged, so "50% año 1 y 2" read as one tier or as
    two means the same."""
    tiers: list[tuple] = []
    for t in rule.tiers:
        prev = tiers[-1] if tiers else None
        if prev and prev[2] == t.pct and prev[1] is not None and prev[1] + 1 == t.from_month:
            tiers[-1] = (prev[0], t.to_month, t.pct)
        else:
            tiers.append((t.from_month, t.to_month, t.pct))
    fee = (rule.fee.total, rule.fee.mode, rule.fee.value) if rule.fee else None
    return tuple(tiers), rule.do_not_pay, fee


def outcome(expected: tuple | None, rule: CommissionRule) -> str:
    if rule.issues:
        return "ok" if expected is None else "flagged"
    if expected is not None and meaning(rule) == expected:
        return "ok"
    return "WRONG"


def _decimal(x) -> Decimal:
    return Decimal(str(x))


def expected_rule(spec: dict, deal: Deal) -> CommissionRule:
    """The rule a case's ``expected`` block describes."""
    fee = spec.get("fee")
    return CommissionRule(
        deal_id=deal.deal_id,
        tiers=tuple(Tier(from_month=a, to_month=b, pct=_decimal(p)) for a, b, p in spec["tiers"]),
        on_total=deal.commission_on_expansion,
        do_not_pay=spec.get("do_not_pay", False),
        fee=FeeDeduction(total=_decimal(fee["total"]), mode=fee["mode"], value=_decimal(fee["value"]))
        if fee else None,
        source_text="",
    )


def invented_cases() -> list[Case]:
    cases = []
    for c in json.loads(CASES_FILE.read_text()):
        deal = Deal(deal_id=c["id"], nombre_negocio="Cliente Prueba", partner="Partner Prueba",
                    partner_commission_pct=c["pct"], partner_commission_notes=c.get("notes"),
                    commission_on_expansion=c.get("commission_on_expansion", False),
                    amount_by_contract=Decimal(100))
        expected = None if c["expected"] == "revision" else meaning(expected_rule(c["expected"], deal))
        cases.append(Case(c["id"], c["kind"], str(c.get("batch", 1)), deal, expected, c["why"]))
    return cases


def real_cases() -> list[Case]:
    cases = []
    for deal in load_inputs().deals:
        ref = reference_rule(deal)
        expected = None if ref.issues else meaning(ref)
        why = "; ".join(ref.issues) if ref.issues else "reference rule"
        cases.append(Case(deal.deal_id, "real", "real", deal, expected, why))
    return cases


def _show(expected: tuple | None, rule: CommissionRule | None = None) -> str:
    if rule is not None:
        return REVIEW if rule.issues else describe_rule(rule)
    if expected is None:
        return REVIEW
    tiers, do_not_pay, fee = expected
    parts = [", ".join(f"m{a}-{'sin fin' if b is None else f'm{b}'}: {p}%" for a, b, p in tiers)]
    if do_not_pay:
        parts.append("no pagar")
    if fee:
        parts.append(f"fee {fee[0]} ({fee[1]} {fee[2]})")
    return "; ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--set", choices=["all", "real", "invented"], default="all")
    args = parser.parse_args()

    cases = (real_cases() if args.set in ("all", "real") else []) + \
            (invented_cases() if args.set in ("all", "invented") else [])
    results: dict[str, list[tuple[str, CommissionRule]]] = {c.id: [] for c in cases}
    model = temperature = None
    for n in range(1, args.runs + 1):
        print(f"run {n}/{args.runs}: reading {len(cases)} texts...", flush=True)
        result = read_rules([c.deal for c in cases], refresh=True)
        if result.error:
            print(f"cannot read rules: {result.error}")
            return 2
        model, temperature = result.model, result.temperature
        for c in cases:
            rule = result.rules[c.id]
            results[c.id].append((outcome(c.expected, rule), rule))

    print(f"\n== {len(cases)} cases × {args.runs} run(s), {model}, temperature {temperature} ==")
    totals, by_kind, by_batch, unstable = Counter(), {}, {}, []
    for c in cases:
        runs = results[c.id]
        outcomes = [o for o, _ in runs]
        totals.update(outcomes)
        by_kind.setdefault(c.kind, Counter()).update(outcomes)
        by_batch.setdefault(c.batch, Counter()).update(outcomes)
        signatures = {(o, REVIEW if r.issues else meaning(r)) for o, r in runs}
        stable = len(signatures) == 1
        if not stable:
            unstable.append(c.id)
        mark = "" if stable else "  UNSTABLE"
        print(f"{c.id:26} {c.kind:15} {' '.join(f'{o:7}' for o in outcomes)}{mark}")
        if any(o != "ok" for o in outcomes) or not stable:
            print(f"    text: {c.deal.partner_commission_pct!r}"
                  + (f" / notes: {c.deal.partner_commission_notes!r}" if c.deal.partner_commission_notes else ""))
            print(f"    expected: {_show(c.expected)}  ({c.why})")
            for i, (o, r) in enumerate(runs, 1):
                print(f"    run {i}: {o:7} {_show(None, r)}")
                for issue in r.issues:
                    print(f"           · {issue}")

    def line(counts):
        return "  ".join(f"{k} {counts[k]}" for k in ("ok", "flagged", "WRONG") if counts[k])

    print("\n== By kind (readings) ==")
    for kind, counts in by_kind.items():
        print(f"{kind:15} {line(counts)}")
    print("\n== By batch (readings) ==")
    for batch, counts in by_batch.items():
        print(f"{batch:15} {line(counts)}")
    total = sum(totals.values())
    print(f"\nreadings: {total} · ok {totals['ok']} · flagged {totals['flagged']} · WRONG {totals['WRONG']}"
          f" · unstable cases {len(unstable)}")
    return 1 if totals["WRONG"] else 0


if __name__ == "__main__":
    sys.exit(main())
