"""Hand-written commission rules for the 8 deals in ``data/``.

They are the reference answers the LLM parser (phase 4) is tested against,
and, until that parser exists, the rules the calculation uses. Only the
meaning of the free text is written here; the base always comes from the
deal's ``commission_on_expansion`` column (D-17).
"""

import hashlib
from decimal import Decimal

from calculator.models import CommissionRule, Deal, FeeDeduction, Tier

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
    # "... deben el partner fee de 1.500usd ... 50% año 1 y 30% año 2 en adelante ..."
    # "Ir descontando" doesn't say how much per payment (D-13).
    "D04": {"tiers": (_YEAR_1, _YEAR_2_ON),
            "fee": FeeDeduction(total=Decimal(1500), mode="unspecified")},
    # "50% año 1 - 30% año 2 en adelante (incluye revenue exp)"
    "D05": {"tiers": (_YEAR_1, _YEAR_2_ON)},
    # "50% - 1er año": 12 months at most (D-11)
    "D06": {"tiers": (_YEAR_1,)},
    # "50% 1er año"
    "D07": {"tiers": (_YEAR_1,)},
    # "50% año 1"
    "D08": {"tiers": (_YEAR_1,)},
}


def rule_text_hash(deal: Deal) -> str:
    """Hash of the text a rule is read from, so a changed text is noticed (D-16)."""
    text = f"{deal.partner_commission_pct}\n{deal.partner_commission_notes or ''}"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def reference_rule(deal: Deal) -> CommissionRule | None:
    """The hand-written rule for ``deal``, or None if there isn't one."""
    meaning = _MEANING.get(deal.deal_id)
    if meaning is None:
        return None
    return CommissionRule(
        deal_id=deal.deal_id,
        on_total=deal.commission_on_expansion,
        source_hash=rule_text_hash(deal),
        **meaning,
    )
