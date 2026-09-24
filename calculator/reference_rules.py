"""Hand-written commission rules for the 8 deals in ``data/``.

They are the reference answers the LLM readings are evaluated against
(``tests/eval_rules.py``), and the rules the calculation tests use. Only the
meaning of the free text is written here; the base always comes from the
deal's ``commission_on_expansion`` column (D-17).
"""

from decimal import Decimal

from calculator.models import CommissionRule, Deal, Tier
from calculator.rules import rule_text

_YEAR_1 = Tier(from_month=1, to_month=12, pct=Decimal(50))
_YEAR_2_ON = Tier(from_month=13, to_month=None, pct=Decimal(30))

# What each deal's partner_commission_pct / partner_commission_notes say.
_MEANING: dict[str, dict] = {
    # "25% - 12 meses"
    "D01": {"tiers": (Tier(from_month=1, to_month=12, pct=Decimal(25)),)},
    # "50% año 1 / 30% perpetuo"
    "D02": {"tiers": (_YEAR_1, _YEAR_2_ON)},
    # "Actualizar Excel pero NO PAGAR - 35% - 24 meses Sobre TOTALIDAD"
    "D03": {"tiers": (Tier(from_month=1, to_month=24, pct=Decimal(35)),), "do_not_pay": True},
    # "... deben el partner fee de 1.500usd ... ir descontando ... hasta cubrir ese monto ..."
    # It never says how much per payment, so the fee is incomplete and the
    # rule can't be used (D-13, D-44).
    "D04": {"tiers": (_YEAR_1, _YEAR_2_ON),
            "issues": ("el texto menciona un partner fee incompleto",)},
    # "50% año 1 - 30% año 2 en adelante (incluye revenue exp)"
    "D05": {"tiers": (_YEAR_1, _YEAR_2_ON)},
    # "50% - 1er año": 12 months at most (D-11)
    "D06": {"tiers": (_YEAR_1,)},
    # "50% 1er año"
    "D07": {"tiers": (_YEAR_1,)},
    # "50% año 1"
    "D08": {"tiers": (_YEAR_1,)},
}


def reference_rule(deal: Deal) -> CommissionRule | None:
    """The hand-written rule for ``deal``, or None if there isn't one."""
    meaning = _MEANING.get(deal.deal_id)
    if meaning is None:
        return None
    return CommissionRule(
        deal_id=deal.deal_id,
        on_total=deal.commission_on_expansion,
        source_text=rule_text(deal),
        **meaning,
    )
