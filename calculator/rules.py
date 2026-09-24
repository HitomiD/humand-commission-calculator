"""Commission rules read by the LLM (pipeline step 3).

The LLM sees only a deal's two rule fields (D-17) and fills a
``RuleExtraction``. ``to_rule`` validates that into the ``CommissionRule``
the calculation uses. Anything wrong or uncertain becomes an entry in the
rule's ``issues``, never an exception, and a rule with issues sends its
deal's payments to review (D-35).
"""

from decimal import Decimal

from pydantic import ValidationError

from calculator.models import CommissionRule, Deal, FeeDeduction, RuleExtraction, Tier, tier_issues


def rule_text(deal: Deal) -> str:
    """The text a deal's rule is read from: its two rule fields, labelled (D-17).

    This exact text is what the LLM sees and what the rule keeps (D-38).
    """
    return (f"partner_commission_pct: {deal.partner_commission_pct}\n"
            f"partner_commission_notes: {deal.partner_commission_notes or ''}")


def _decimal(x: float) -> Decimal:
    """A number from the LLM as a Decimal, without float noise: 50.0 → 50, 12.5 → 12.5."""
    d = Decimal(str(x))
    return d.quantize(Decimal(1)) if d == d.to_integral_value() else d


def _month_range(from_month: int, to_month: int | None) -> str:
    return f"m{from_month}-" + ("sin fin" if to_month is None else f"m{to_month}")


def to_rule(extraction: RuleExtraction, deal: Deal) -> CommissionRule:
    """Validate what the LLM read into the rule the calculation uses (D-18).

    Checks the tiers (valid percentages, starting at month 1, no gaps or
    overlaps), that the fee's mode and value agree, and that a base the text
    mentions agrees with ``commission_on_expansion``, which always wins
    (D-17). The LLM's own flags become issues too. There is no separate
    duration to check: the maximum comes from the last tier (D-31).
    """
    issues: list[str] = []

    tiers = []
    for t in extraction.tiers:
        try:
            tiers.append(Tier(from_month=t.from_month, to_month=t.to_month, pct=_decimal(t.pct)))
        except ValidationError:
            issues.append(f"tramo inválido: {_month_range(t.from_month, t.to_month)} al {t.pct}%")
    if not issues:  # the order only makes sense when every tier is valid
        issues += tier_issues(tuple(tiers))

    fee = None
    if (f := extraction.fee) is not None:
        try:
            fee = FeeDeduction(total=_decimal(f.total), mode=f.mode,
                               value=None if f.value is None else _decimal(f.value))
        except ValidationError:
            issues.append(f"partner fee inválido: total {f.total}, modo {f.mode}, valor {f.value}")

    said = extraction.base_mencionada
    if said is not None and (said == "total") != deal.commission_on_expansion:
        column = "Yes" if deal.commission_on_expansion else "No"
        issues.append(f"el texto menciona la base '{said}' pero commission_on_expansion es {column}")

    issues += [f"el modelo marcó: {flag.strip()}" for flag in extraction.flags if flag.strip()]

    return CommissionRule(
        deal_id=deal.deal_id,
        tiers=tuple(tiers),
        on_total=deal.commission_on_expansion,
        do_not_pay=extraction.do_not_pay,
        fee=fee,
        issues=tuple(issues),
        source_text=rule_text(deal),
    )
