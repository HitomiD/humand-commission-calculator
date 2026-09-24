"""Commission calculation (pipeline steps 4–6): pure functions, no I/O.

Given the loaded inputs, the fetched payments and a rule per deal, this
produces one ``CommissionLine`` per new payment. Months are counted
sequentially per deal and dates are ignored (D-01).
"""

from collections.abc import Callable, Iterable
from decimal import ROUND_HALF_UP, Decimal

from calculator.data import InputData
from calculator.models import (
    ApprovedPayment, CommissionLine, CommissionRule, Deal, FeeDeduction, Payment, Tier,
    TierSlice, Trace,
)
from calculator.payments import FetchResult

CENT = Decimal("0.01")


# --- Step 4: reconcile ----------------------------------------------------

def months_already(approved: Iterable[ApprovedPayment], blocked: set[str]) -> dict[str, int | None]:
    """Months already commissioned per deal: the sum of ``meses_cubiertos`` (D-04).

    A blocked deal gets None: its approved rows can't be trusted (D-22).
    """
    totals: dict[str, int | None] = {d: None for d in blocked}
    for a in approved:
        if a.deal_id not in blocked:
            totals[a.deal_id] = totals.get(a.deal_id, 0) + a.meses_cubiertos
    return totals


# --- Step 6: compute, one piece at a time ---------------------------------

def eligible_range(already: int, covered: int, max_months: int | None) -> tuple[int, int] | None:
    """Months this payment commissions: the next ``covered`` months, cut at
    ``max_months`` (D-09). None when no month remains."""
    start, end = already + 1, already + covered
    if max_months is not None:
        end = min(end, max_months)
    return (start, end) if start <= end else None


def tier_breakdown(start: int, end: int, tiers: Iterable[Tier], base: Decimal) -> list[TierSlice]:
    """Split ``start..end`` across the tiers and price each part (D-10). Not rounded."""
    slices = []
    for t in tiers:
        lo, hi = max(start, t.from_month), min(end, t.to_month or end)
        if lo <= hi:
            months = hi - lo + 1
            slices.append(TierSlice(from_month=lo, to_month=hi, pct=t.pct, months=months,
                                    amount=months * base * t.pct / 100))
    return slices


def base_mensual(deal: Deal, payment: Payment) -> Decimal:
    """Monthly base (D-07): the payment spread over its months when the deal
    commissions on the total, otherwise the contract amount."""
    if deal.commission_on_expansion:
        return payment.amount / payment.payment_term.months
    return deal.amount_by_contract


def remaining_after(end: int, max_months: int | None) -> int | None:
    """Months left after ``end``; None when the rule has no limit."""
    return None if max_months is None else max_months - end


def estado(remaining: int | None) -> str:
    """D-12: no limit → en_curso; nothing left → completo; otherwise incompleto."""
    if remaining is None:
        return "en_curso"
    return "completo" if remaining == 0 else "incompleto"


def memo(deal: Deal, start: int, end: int, remaining: int | None) -> str:
    """Transfer memo, in the expected output's exact format."""
    left = "sin_limite" if remaining is None else str(remaining)
    return f"{deal.nombre_negocio} - comision pago m{start}-m{end} - restan {left}"


def fee_deduction(fee: FeeDeduction, gross: Decimal, balance: Decimal) -> Decimal:
    """How much of the fee this commission recovers (D-13). Never more than
    the balance owed or the commission itself. ``fee.mode`` must be known."""
    if fee.mode == "fixed_per_payment":
        wanted = fee.value
    elif fee.mode == "pct_of_commission":
        wanted = gross * fee.value / 100
    else:  # as_much_as_possible
        wanted = gross
    return min(wanted, balance, gross)


def round_money(amount: Decimal) -> Decimal:
    """Round once, at the end, to cents, half-up (D-14)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


# --- One payment ----------------------------------------------------------

def compute_line(
    deal: Deal, rule: CommissionRule, payment: Payment, already: int,
    fee_balance: Decimal | None = None,
) -> CommissionLine:
    """The line for one new payment of a deal whose inputs are trusted.

    ``fee_balance`` is what's still owed of the rule's fee, or None when it
    can't be known.
    """
    covered = payment.payment_term.months
    base = base_mensual(deal, payment)
    common = {
        "deal_id": deal.deal_id,
        "payment_id": payment.payment_id,
        "partner": deal.partner,
        "base_usada": "totalidad(stripe)" if deal.commission_on_expansion else "contrato",
        "base_mensual": round_money(base),
    }
    months = eligible_range(already, covered, rule.max_months)

    def trace(slices=(), flags=(), **fee) -> Trace:
        return Trace(rule=rule, months_before=already, months_in_payment=covered,
                     payment_amount=payment.amount, base_mensual=base,
                     slices=tuple(slices), flags=tuple(flags), **fee)

    # A client pays exactly what they owe or more (expansion); less is an
    # error in the payment, whatever the base (D-08).
    if payment.amount / covered < deal.amount_by_contract:
        return CommissionLine(**common, estado="requiere_revision", trace=trace(),
                              reason=(f"el pago de {payment.amount} por {covered} mes(es) es menor "
                                      f"al monto de contrato de {deal.amount_by_contract}/mes"))

    if months is None:
        return CommissionLine(**common, estado="no_corresponde", trace=trace(),
                              reason=f"ya se comisionaron los {rule.max_months} meses")
    start, end = months
    flags = []
    if end < already + covered:
        flags.append(f"el pago cubre m{already + 1}-m{already + covered}; se corta en m{rule.max_months}")
    slices = tier_breakdown(start, end, rule.tiers, base)
    common["meses_elegibles"] = f"m{start}-m{end}"

    if rule.do_not_pay:
        # The months are used up (the notes say to update the sheet) but nothing is paid (D-29).
        return CommissionLine(**common, estado="no_corresponde", trace=trace(slices, flags),
                              reason="las notas del deal dicen que no se pague")

    gross = sum((s.amount for s in slices), Decimal(0))
    fee_fields = {}
    if rule.fee is not None:
        if rule.fee.mode == "unspecified":
            return CommissionLine(**common, estado="requiere_revision", trace=trace(slices, flags),
                                  reason=(f"hay un partner fee de {rule.fee.total} a descontar, pero la regla "
                                          "no dice cuánto por pago"))
        if fee_balance is None:
            return CommissionLine(**common, estado="requiere_revision", trace=trace(slices, flags),
                                  reason=("saldo del partner fee desconocido: el deal tiene pagos aprobados "
                                          "y no hay registro de cuánto fee se descontó en ellos"))
        deducted = fee_deduction(rule.fee, gross, fee_balance)
        fee_fields = {"gross_amount": gross, "fee_deducted": deducted,
                      "fee_balance_after": fee_balance - deducted}
    net = gross - fee_fields.get("fee_deducted", 0)

    remaining = remaining_after(end, rule.max_months)
    if remaining == 0 and fee_fields.get("fee_balance_after", 0) > 0:
        # The rule ends here with fee still owed and no later commission to
        # deduct it from. Collecting it is a business decision (D-13).
        return CommissionLine(**common, estado="requiere_revision",
                              trace=trace(slices, flags, **fee_fields),
                              reason=(f"la regla termina en m{end} con "
                                      f"{round_money(fee_fields['fee_balance_after'])} del partner fee "
                                      "todavía adeudado y sin comisiones posteriores de las que descontarlo"))

    return CommissionLine(
        **common,
        monto_a_comisionar=round_money(net),
        estado=estado(remaining),
        memo=memo(deal, start, end, remaining),
        trace=trace(slices, flags, **fee_fields),
    )


# --- Steps 5 and 6 for the whole run ---------------------------------------

def build_lines(
    inputs: InputData,
    fetched: FetchResult,
    rule_for: Callable[[Deal], CommissionRule | None],
) -> list[CommissionLine]:
    """One line per new payment, plus one per payment error.

    Payments are taken in the order the API served them, and each adds its
    months to its deal's running total before the next (O-03). Anything that
    can't be trusted becomes a ``requiere_revision`` line; nothing is dropped.
    """
    deals = {d.deal_id: d for d in inputs.deals}
    blocked = inputs.blocked_deals
    approved_ids = {a.payment_id for a in inputs.approved}  # step 5 (D-05)
    running = months_already(inputs.approved, blocked)
    with_history = {a.deal_id for a in inputs.approved}
    fee_owed: dict[str, Decimal | None] = {}  # deal_id → fee balance, as lines are built
    held: dict[str, str] = {}  # deal_id → why its later payments can't be computed

    def review(deal_id, payment_id, reason, partner=None):
        return CommissionLine(deal_id=deal_id, payment_id=payment_id, estado="requiere_revision",
                              reason=reason, partner=partner)

    lines = [review(e.deal_id, e.payment_id, f"el pago no se puede usar: {e.message}")
             for e in fetched.errors]

    for p in fetched.payments:
        if p.payment_id in approved_ids:
            continue
        deal = deals.get(p.deal_id)
        if p.deal_id in blocked:
            lines.append(review(p.deal_id, p.payment_id, "el deal tiene problemas en los datos (ver arriba)",
                                deal.partner if deal else None))
            continue
        if deal is None:
            lines.append(review(p.deal_id, p.payment_id, "deal no encontrado en hubspot_deals.csv"))
            continue
        if p.deal_id in held:
            lines.append(review(p.deal_id, p.payment_id, held[p.deal_id], deal.partner))
            continue
        rule = rule_for(deal)
        if rule is None or rule.issues:
            why = "; ".join(rule.issues) if rule else "no hay regla de comisión para este deal"
            lines.append(review(p.deal_id, p.payment_id, f"la regla no se puede usar: {why}", deal.partner))
            continue

        already = running.get(p.deal_id, 0)
        if rule.fee is not None and p.deal_id not in fee_owed:
            # With approved history, part of the fee may already be recovered,
            # and nothing records how much the old manual process deducted (D-13).
            fee_owed[p.deal_id] = None if p.deal_id in with_history else rule.fee.total
        line = compute_line(deal, rule, p, already, fee_owed.get(p.deal_id))
        lines.append(line)
        if line.trace and line.trace.fee_balance_after is not None:
            fee_owed[p.deal_id] = line.trace.fee_balance_after
        if line.estado == "requiere_revision":
            # This payment's months are undecided, so any later one would be a guess.
            held[p.deal_id] = f"un pago anterior ({p.payment_id}) de este deal requiere revisión"
        elif months := eligible_range(already, p.payment_term.months, rule.max_months):
            running[p.deal_id] = months[1]
    return lines
