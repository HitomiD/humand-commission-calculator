"""What the LLM returns when it reads a deal's rule text (D-15, D-18).

``RuleExtraction`` is the schema Gemini must fill. It is kept flat and plain:
numbers are floats, and every field is required but may be null, because
Gemini's structured output accepts only a subset of JSON Schema. Nothing
here is trusted: ``calculator.rules.to_rule`` validates it into a
``CommissionRule``. The field descriptions are sent to the model as part of
the schema, so they are written as instructions, in Spanish like the
prompt (D-39).
"""

from typing import Literal

from pydantic import BaseModel, Field

FeeMode = Literal["unspecified", "fixed_per_payment", "pct_of_commission", "as_much_as_possible"]


class ExtractedTier(BaseModel):
    from_month: int = Field(description="Primer mes de comisión de este tramo, contando desde 1.")
    to_month: int | None = Field(
        description="Último mes de comisión de este tramo, inclusive. Null si el tramo no tiene fin "
                    "('perpetuo', 'en adelante').")
    pct: float = Field(description="Porcentaje de comisión para estos meses, de 0 a 100.")


class ExtractedFee(BaseModel):
    total: float = Field(description="Total del partner fee adeudado, en USD.")
    mode: FeeMode = Field(
        description="Cuánto de cada comisión va al fee, según lo dice el texto. "
                    "'unspecified' si el texto no dice cuánto por pago.")
    value: float | None = Field(
        description="USD por pago para 'fixed_per_payment', porcentaje de cada comisión para "
                    "'pct_of_commission'; null para los otros modos.")


class RuleExtraction(BaseModel):
    tiers: list[ExtractedTier] = Field(
        description="Tramos de comisión en orden, desde el mes 1, sin huecos ni superposiciones.")
    do_not_pay: bool = Field(description="True si el texto dice que esta comisión no se debe pagar.")
    fee: ExtractedFee | None = Field(description="Partner fee a recuperar de las comisiones, o null.")
    base_mencionada: Literal["total", "contrato"] | None = Field(
        description="La base que menciona el texto: 'total' para la totalidad de lo facturado (p. ej. "
                    "'sobre la totalidad'), 'contrato' para el monto de contrato; null si no menciona ninguna.")
    flags: list[str] = Field(
        description="Lo ambiguo, contradictorio o que este esquema no cubre, en castellano, "
                    "una oración corta cada uno. Vacío si el texto es claro.")
