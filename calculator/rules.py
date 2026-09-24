"""Commission rules read by the LLM (pipeline step 3).

The LLM sees only a deal's two rule fields (D-17) and fills a
``RuleExtraction``. ``to_rule`` validates that into the ``CommissionRule``
the calculation uses. Anything wrong or uncertain becomes an entry in the
rule's ``issues``, never an exception, and a rule with issues sends its
deal's payments to review (D-35).

``read_rules`` asks Gemini to read every deal on each run, in parallel
(D-37). A warm instance remembers the readings in memory, keyed by model and
text; ``refresh=True`` ignores them and asks again. A deal whose text can't be
read gets a rule with an issue, and the run goes on.
"""

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal

from google import genai
from google.genai import types
from pydantic import ValidationError

from calculator import config
from calculator.models import CommissionRule, Deal, FeeDeduction, RuleExtraction, Tier, tier_issues

# What the model is told, in Spanish like the texts, with invented examples
# of each kind of rule (D-39).
# The real deals' texts are left out, so the evaluation against the reference
# rules isn't a test of copying.
INSTRUCTIONS = """\
Leés las condiciones de comisión de un deal y completás el esquema JSON dado.
El partner que trajo al cliente cobra un porcentaje de lo que el cliente paga,
mes a mes. El texto está escrito a mano y puede ser desprolijo.

Regla general: extraé solo lo que el texto dice. Si a un campo le falta un
dato para poder calcular la comisión, no lo completes ni lo supongas: dejalo
vacío (null o lista vacía) y explicá en flags qué falta. Los flags son para lo
que impide calcular: datos que faltan, ambigüedades, contradicciones o reglas
que el esquema no puede expresar (por ejemplo un umbral, o varios partners).

Meses:
- La comisión se cuenta por meses, no por pagos: un solo pago del cliente
  puede cubrir varios meses (mensual, trimestral, anual). Si la regla se
  define por pagos en vez de meses, no la conviertas a meses: tiers vacío y un flag.
- Se cuentan desde 1, el primer mes comisionado.
- "año 1" / "1er año" / "primer año" son los meses 1-12; "año 2" son 13-24, y así.
- Cada tramo necesita una duración: una cantidad de meses o años, un mes final,
  o palabras que digan que no tiene fin ("perpetuo", "de por vida", "en
  adelante": to_month null). Si el texto no dice la duración, no la supongas:
  tiers vacío y un flag.
- Un solo porcentaje por "N meses" es un tramo de 1 a N.
- No agregues tramos que el texto no dice.

Otros campos:
- do_not_pay: true solo si el texto dice que no se pague. Igual completá los tramos.
- menciona_fee: true si el texto menciona un partner fee o una deuda del
  partner a descontar de sus comisiones, esté completa o no.
- fee: solo si el texto dice el total adeudado y cuánto descontar de cada
  comisión (un monto fijo por pago o un porcentaje de cada comisión). Si falta
  alguno de los dos, fee es null y va un flag.
- base_mencionada: solo si el texto nombra la base explícitamente: "total"
  para la totalidad de lo facturado, "contrato" para el monto de contrato. Si
  no, null. La base sale de otro dato, así que una duda sobre la base no es un flag.
- Ignorá lo que no habla de la comisión, como el tipo de partner o notas administrativas.
- Escribí los flags en castellano, una oración corta cada uno.

Ejemplos:
"30% - 6 meses" -> tiers [1-6: 30]
"40% año 1 / 20% año 2" -> tiers [1-12: 40, 13-24: 20]
"20% primer año, luego 10% en adelante" -> tiers [1-12: 20, 13-null: 10]
"15% de por vida sobre el total facturado" -> tiers [1-null: 15], base_mencionada "total"
"No abonar. 20% 12 meses" -> tiers [1-12: 20], do_not_pay true
"Deben 800usd de fee; descontar 100usd de cada comisión. 30% año 1" -> tiers [1-12: 30],
  menciona_fee true, fee {total 800, mode fixed_per_payment, value 100}
"Fee de 600 usd: se retiene el 25% de cada comisión. 20% año 1" -> tiers [1-12: 20],
  menciona_fee true, fee {total 600, mode pct_of_commission, value 25}
"Fee pendiente de 500 usd a recuperar de las comisiones. 25% año 1" -> tiers [1-12: 25],
  menciona_fee true, fee null, flags ["menciona un fee de 500 USD pero no dice cuánto descontar de cada comisión"]
"35% o 40% según volumen" -> tiers [], flags ["el porcentaje depende del volumen y no se indica cuál aplica"]
"""


class ExtractionError(Exception):
    """Gemini answered, but not with a usable reading."""


def extract(text: str, *, api_key: str, model: str) -> RuleExtraction:
    """Ask Gemini to read one rule text. Raises on any failure (D-36).

    Retries on rate limits and server errors are left to the SDK.
    """
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=60_000,  # ms
        retry_options=types.HttpRetryOptions(attempts=5, http_status_codes=[408, 429, 500, 502, 503, 504]),
    ))
    response = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS,
            temperature=0,
            response_mime_type="application/json",
            response_schema=RuleExtraction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    if not isinstance(response.parsed, RuleExtraction):
        raise ExtractionError(f"respuesta sin un JSON válido: {(response.text or '')[:200]!r}")
    return response.parsed


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
    overlaps), that a fee the text mentions is complete (D-44), and that a
    base the text mentions agrees with ``commission_on_expansion``, which
    always wins (D-17). The LLM's own flags become issues too. There is no separate
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
            fee = FeeDeduction(total=_decimal(f.total), mode=f.mode, value=_decimal(f.value))
        except ValidationError:
            issues.append(f"partner fee inválido: total {f.total}, modo {f.mode}, valor {f.value}")
        if not extraction.menciona_fee:
            issues.append("el modelo devolvió un partner fee pero indicó que el texto no menciona ninguno")
    elif extraction.menciona_fee:
        # Checked here, not left to the model's flags: an incomplete fee that
        # were simply dropped would pay the partner in full and lose the debt (D-44).
        issues.append("el texto menciona un partner fee incompleto")

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


@dataclass(frozen=True)
class RulesResult:
    rules: dict[str, CommissionRule]  # by deal_id
    model: str  # which model read them (D-38)
    error: str | None = None  # a problem affecting every deal, shown once
    # What the model returned for each deal, before validation; None when it
    # couldn't be read. Kept so the page can show every step (D-41).
    readings: dict[str, RuleExtraction | None] = field(default_factory=dict)


# (model, text) → reading, for as long as this instance lives (D-37). Only
# good readings are kept, so a failed one is tried again on the next run.
_readings: dict[tuple[str, str], RuleExtraction] = {}


def _unreadable(deal: Deal, why: str) -> CommissionRule:
    return CommissionRule(deal_id=deal.deal_id, tiers=(), on_total=deal.commission_on_expansion,
                          issues=(why,), source_text=rule_text(deal))


def read_rules(deals: Iterable[Deal], *, refresh: bool = False) -> RulesResult:
    """Every deal's rule, read by Gemini. Never raises: a deal that can't be
    read gets a rule with an issue, so its payments go to review."""
    deals = list(deals)
    model = config.gemini_model()
    try:
        api_key = config.gemini_api_key()
    except config.ConfigError as e:
        return RulesResult({d.deal_id: _unreadable(d, f"no se pudo leer la regla: {e}") for d in deals},
                           model, str(e))

    def read(deal: Deal) -> tuple[CommissionRule, RuleExtraction | None]:
        text = rule_text(deal)
        key = (model, text)
        if refresh or key not in _readings:
            try:
                _readings[key] = extract(text, api_key=api_key, model=model)
            except Exception as e:  # noqa: BLE001 — one deal's failure must not stop the run
                why = f"no se pudo leer la regla con {model}: {type(e).__name__}: {e}"
                return _unreadable(deal, why), None
        return to_rule(_readings[key], deal), _readings[key]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read, deals))
    return RulesResult({rule.deal_id: rule for rule, _ in results}, model,
                       readings={rule.deal_id: reading for rule, reading in results})


def describe_rule(rule: CommissionRule) -> str:
    """A rule in one short line, for the page and the evaluation:
    ``m1-m12: 50%, m13-sin fin: 30%; fee 1500 (fixed_per_payment 100)``."""
    parts = [", ".join(f"{_month_range(t.from_month, t.to_month)}: {t.pct}%" for t in rule.tiers)
             or "sin tramos"]
    if rule.do_not_pay:
        parts.append("no pagar")
    if rule.fee:
        parts.append(f"fee {rule.fee.total} ({rule.fee.mode} {rule.fee.value})")
    return "; ".join(parts)
