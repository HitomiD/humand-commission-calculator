"""Input models: rows loaded from the CSV files in ``data/``.

They validate each row so that malformed data fails loudly at load time
instead of producing a wrong commission later.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _InputRow(BaseModel):
    """Base for CSV rows: immutable, and blank cells become ``None``."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class Deal(_InputRow):
    """One row of ``hubspot_deals.csv``: a client deal and its commission terms."""

    deal_id: str
    nombre_negocio: str  # client name, used in the memo
    partner: str  # grouping key for partner transfers
    type_of_partner: str | None = None
    type_of_partner_for_this_deal: str | None = None
    # Free-text commission rule, parsed by the LLM.
    partner_commission_pct: str
    partner_commission_notes: str | None = None
    # True: commission on the full Stripe payment. False: on the contract amount.
    commission_on_expansion: bool
    amount_by_contract: Decimal = Field(gt=0)  # monthly contract amount (USD)
    # Informational only; not used in the calculation (decisions D-01, D-02).
    estado_pago_comision: str | None = None
    date_of_first_payment: date | None = None

    @field_validator("commission_on_expansion", mode="before")
    @classmethod
    def _parse_yes_no(cls, value):
        # Only the CSV's exact vocabulary is accepted, so a typo cannot silently
        # switch the base between contract and total.
        if isinstance(value, bool):
            return value
        mapping = {"yes": True, "no": False}
        if isinstance(value, str) and value.lower() in mapping:
            return mapping[value.lower()]
        raise ValueError(f"expected 'Yes' or 'No', got {value!r}")


class ApprovedPayment(_InputRow):
    """One row of ``pagos_aprobados.csv``: a commission already paid out.

    Rows are per historical payment, not per month: an annual payment is one
    row with ``meses_cubiertos = 12`` (decision D-04).
    """

    deal_id: str
    payment_id: str
    meses_cubiertos: int = Field(ge=1)


class PaymentTerm(str, Enum):
    """Billing period of a payment; the value is the mock API's Spanish label."""

    MENSUAL = "mensual"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"

    @property
    def months(self) -> int:
        """Commission months a payment of this term covers (decision D-03)."""
        return {"mensual": 1, "trimestral": 3, "semestral": 6, "anual": 12}[self.value]


class Payment(BaseModel):
    """One client payment returned by the mock Stripe endpoint."""

    model_config = ConfigDict(frozen=True)

    deal_id: str
    payment_id: str  # unique; also the key for de-duplicating fetched pages
    payment_date: date  # informational only (decision D-01)
    amount: Decimal = Field(gt=0)  # total paid, covering the whole term
    payment_term: PaymentTerm  # an unknown term is rejected, never guessed
    currency: Literal["USD"]  # the challenge states all amounts are in USD
