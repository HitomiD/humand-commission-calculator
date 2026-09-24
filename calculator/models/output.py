"""Calculation output: one ``CommissionLine`` per new payment, with its trace."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from calculator.models.rules import CommissionRule

Estado = Literal["completo", "incompleto", "en_curso", "no_corresponde", "requiere_revision"]
BaseUsada = Literal["contrato", "totalidad(stripe)"]  # labels from the expected output


class TierSlice(BaseModel):
    """The part of a line's month range that falls inside one tier."""

    model_config = ConfigDict(frozen=True)

    from_month: int
    to_month: int
    pct: Decimal
    months: int
    amount: Decimal  # not rounded; the line rounds the total once (D-14)


class Trace(BaseModel):
    """How a line's numbers were reached, so each one can be checked."""

    model_config = ConfigDict(frozen=True)

    rule: CommissionRule  # copy of the rule used (D-16)
    months_before: int  # months already commissioned before this payment
    months_in_payment: int  # from payment_term (D-03)
    payment_amount: Decimal
    base_mensual: Decimal  # not rounded
    slices: tuple[TierSlice, ...] = ()
    flags: tuple[str, ...] = ()
    # Only when the rule has a fee (D-13); amounts not rounded.
    gross_amount: Decimal | None = None  # sum of the slices, before the fee
    fee_deducted: Decimal | None = None
    fee_balance_after: Decimal | None = None


class CommissionLine(BaseModel):
    """One output row. The first eight fields are the expected output's columns."""

    model_config = ConfigDict(frozen=True)

    deal_id: str | None
    payment_id: str | None
    base_usada: BaseUsada | None = None
    base_mensual: Decimal | None = None  # rounded to 2 decimals for display
    meses_elegibles: str | None = None  # "m5-m16"; None when no months apply
    monto_a_comisionar: Decimal = Decimal("0.00")
    estado: Estado
    memo: str | None = None
    # Added by us:
    partner: str | None = None
    reason: str | None = None  # why a line is no_corresponde or requiere_revision
    trace: Trace | None = None


class PartnerTransfer(BaseModel):
    """One partner's commissions for the run, as a single transfer (step 7).

    Only lines with a memo are paid; the partner's lines in review are listed
    beside the transfer so they aren't forgotten, but not paid.
    """

    model_config = ConfigDict(frozen=True)

    partner: str
    lines: tuple[CommissionLine, ...]  # paid in this transfer
    total: Decimal
    memo: str | None  # combined memo (D-42); None when nothing is paid
    pending: tuple[CommissionLine, ...] = ()  # requiere_revision, not paid
