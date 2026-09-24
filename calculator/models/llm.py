"""What the LLM returns when it reads a deal's rule text (D-15, D-18).

``RuleExtraction`` is the schema Gemini must fill. It is kept flat and plain:
numbers are floats, and every field is required but may be null, because
Gemini's structured output accepts only a subset of JSON Schema. Nothing
here is trusted: ``calculator.rules.to_rule`` validates it into a
``CommissionRule``. The field descriptions are sent to the model as part of
the schema, so they are written as instructions.
"""

from typing import Literal

from pydantic import BaseModel, Field

FeeMode = Literal["unspecified", "fixed_per_payment", "pct_of_commission", "as_much_as_possible"]


class ExtractedTier(BaseModel):
    from_month: int = Field(description="First commission month of this tier, counting from 1.")
    to_month: int | None = Field(
        description="Last commission month of this tier, inclusive. Null when the tier has no end "
                    "('perpetuo', 'en adelante').")
    pct: float = Field(description="Commission percentage for these months, from 0 to 100.")


class ExtractedFee(BaseModel):
    total: float = Field(description="Total partner fee owed, in USD.")
    mode: FeeMode = Field(
        description="How much of each commission goes to the fee, as the text states it. "
                    "'unspecified' when the text doesn't say how much per payment.")
    value: float | None = Field(
        description="USD per payment for 'fixed_per_payment', percentage of each commission for "
                    "'pct_of_commission'; null for the other modes.")


class RuleExtraction(BaseModel):
    tiers: list[ExtractedTier] = Field(
        description="Commission tiers in order, starting at month 1, with no gaps or overlaps.")
    do_not_pay: bool = Field(description="True when the text says this commission must not be paid.")
    fee: ExtractedFee | None = Field(description="Partner fee to recover from commissions, or null.")
    base_mencionada: Literal["total", "contrato"] | None = Field(
        description="The base the text mentions: 'total' for the whole amount billed (e.g. 'sobre la "
                    "totalidad'), 'contrato' for the contract amount; null when it mentions none.")
    flags: list[str] = Field(
        description="Anything ambiguous, contradictory or not covered by this schema, in Spanish, "
                    "one short sentence each. Empty when the text is clear.")
