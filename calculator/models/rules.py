"""Commission rules: what a deal's free-text terms mean, in a form the
calculation can use.

In phase 3 the rules are written by hand (``calculator/reference_rules.py``);
in phase 4 the LLM's output is validated into the same model (D-18).
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Tier(BaseModel):
    """One percentage over a range of commission months (1-based, inclusive)."""

    model_config = ConfigDict(frozen=True)

    from_month: int = Field(ge=1)
    to_month: int | None = Field(default=None, ge=1)  # None: no end
    pct: Decimal = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self):
        if self.to_month is not None and self.to_month < self.from_month:
            raise ValueError(f"tier ends (m{self.to_month}) before it starts (m{self.from_month})")
        return self


def tier_issues(tiers: tuple[Tier, ...]) -> list[str]:
    """Problems that make a set of tiers unusable; empty when they're fine.

    Tiers must start at month 1 and follow on without gaps or overlaps, and
    only the last one may be open-ended.
    """
    if not tiers:
        return ["sin tramos"]
    issues = []
    if tiers[0].from_month != 1:
        issues.append(f"el primer tramo empieza en m{tiers[0].from_month}, no en m1")
    for prev, cur in zip(tiers, tiers[1:]):
        if prev.to_month is None:
            issues.append(f"el tramo sin fin desde m{prev.from_month} no es el último")
        elif cur.from_month != prev.to_month + 1:
            issues.append(f"al tramo que termina en m{prev.to_month} le sigue uno que empieza en m{cur.from_month}")
    return issues


class FeeDeduction(BaseModel):
    """A partner fee recovered from the partner's commissions (D-13, D-44).

    Only a complete fee exists: the total owed and how much is taken from
    each commission, as the rule text states it:
    - ``fixed_per_payment``: ``value`` USD from each commission.
    - ``pct_of_commission``: ``value`` % of each commission.
    A text that mentions a fee without saying both has no ``FeeDeduction``:
    its rule gets an issue and the deal goes to review.
    """

    model_config = ConfigDict(frozen=True)

    total: Decimal = Field(gt=0)
    mode: Literal["fixed_per_payment", "pct_of_commission"]
    value: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def _pct_at_most_100(self):
        if self.mode == "pct_of_commission" and self.value > 100:
            raise ValueError("pct_of_commission above 100")
        return self


class CommissionRule(BaseModel):
    """Everything the calculation needs to know about how a deal is paid.

    ``on_total`` comes from the deal's ``commission_on_expansion`` column,
    never from the rule text (D-17). A rule with ``issues`` is not used: its
    deal's payments go to review (D-35).
    """

    model_config = ConfigDict(frozen=True)

    deal_id: str
    tiers: tuple[Tier, ...]
    on_total: bool  # True: base is the payment; False: the contract amount (D-07)
    do_not_pay: bool = False  # e.g. D03 "NO PAGAR"
    fee: FeeDeduction | None = None  # partner fee to recover (D-13)
    issues: tuple[str, ...] = ()
    source_text: str  # the text this rule was read from (D-38)

    @property
    def max_months(self) -> int | None:
        """Last commissionable month; None when the last tier has no end."""
        return self.tiers[-1].to_month if self.tiers else None
