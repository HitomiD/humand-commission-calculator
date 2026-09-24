"""Commission calculation (pipeline steps 4–6): pure functions, no I/O.

Given the loaded inputs, the fetched payments and a rule per deal, this
produces one ``CommissionLine`` per new payment. Months are counted
sequentially per deal and dates are ignored (D-01).
"""

from collections.abc import Callable, Iterable
from decimal import ROUND_HALF_UP, Decimal

from calculator.data import InputData
from calculator.models import (
    ApprovedPayment, CommissionLine, CommissionRule, Deal, Payment, Tier, TierSlice, Trace,
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


def round_money(amount: Decimal) -> Decimal:
    """Round once, at the end, to cents, half-up (D-14)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


# --- One payment ----------------------------------------------------------

def compute_line(deal: Deal, rule: CommissionRule, payment: Payment, already: int) -> CommissionLine:
    """The line for one new payment of a deal whose inputs are trusted."""
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

    def trace(slices=(), flags=()) -> Trace:
        return Trace(rule=rule, months_before=already, months_in_payment=covered,
                     payment_amount=payment.amount, base_mensual=base,
                     slices=tuple(slices), flags=tuple(flags))

    if months is None:
        return CommissionLine(**common, estado="no_corresponde", trace=trace(),
                              reason=f"all {rule.max_months} months were already commissioned")
    start, end = months
    flags = []
    if end < already + covered:
        flags.append(f"payment covers m{already + 1}-m{already + covered}; cut at m{rule.max_months} (D-09)")
    slices = tier_breakdown(start, end, rule.tiers, base)
    common["meses_elegibles"] = f"m{start}-m{end}"

    if rule.do_not_pay:
        # The months are used up (the notes say to update the sheet) but nothing is paid (D-29).
        return CommissionLine(**common, estado="no_corresponde", trace=trace(slices, flags),
                              reason="the deal's notes say not to pay")

    # PENDING D-13: how the partner fee is deducted. Until it's decided, the
    # line is not paid.
    if rule.fee is not None:
        return CommissionLine(**common, estado="requiere_revision", trace=trace(slices, flags),
                              reason=f"partner fee of {rule.fee} to deduct; rule pending (D-13)")

    # PENDING D-08: a payment below the contract amount on a contract base.
    if not deal.commission_on_expansion and payment.amount / covered < deal.amount_by_contract:
        return CommissionLine(**common, estado="requiere_revision", trace=trace(slices, flags),
                              reason="payment is below the contract amount; rule pending (D-08)")

    remaining = remaining_after(end, rule.max_months)
    return CommissionLine(
        **common,
        monto_a_comisionar=round_money(sum((s.amount for s in slices), Decimal(0))),
        estado=estado(remaining),
        memo=memo(deal, start, end, remaining),
        trace=trace(slices, flags),
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
    held: dict[str, str] = {}  # deal_id → why its later payments can't be computed

    def review(deal_id, payment_id, reason, partner=None):
        return CommissionLine(deal_id=deal_id, payment_id=payment_id, estado="requiere_revision",
                              reason=reason, partner=partner)

    lines = [review(e.deal_id, e.payment_id, f"payment can't be used: {e.message}")
             for e in fetched.errors]

    for p in fetched.payments:
        if p.payment_id in approved_ids:
            continue
        deal = deals.get(p.deal_id)
        if p.deal_id in blocked:
            lines.append(review(p.deal_id, p.payment_id, "the deal has data issues (see above)",
                                deal.partner if deal else None))
            continue
        if deal is None:
            lines.append(review(p.deal_id, p.payment_id, "deal not found in hubspot_deals.csv"))
            continue
        if p.deal_id in held:
            lines.append(review(p.deal_id, p.payment_id, held[p.deal_id], deal.partner))
            continue
        rule = rule_for(deal)
        if rule is None or rule.issues:
            why = "; ".join(rule.issues) if rule else "no commission rule for this deal"
            lines.append(review(p.deal_id, p.payment_id, f"rule can't be used: {why}", deal.partner))
            continue

        already = running.get(p.deal_id, 0)
        line = compute_line(deal, rule, p, already)
        lines.append(line)
        if line.estado == "requiere_revision":
            # This payment's months are undecided, so any later one would be a guess.
            held[p.deal_id] = f"an earlier payment ({p.payment_id}) of this deal needs review"
        elif months := eligible_range(already, p.payment_term.months, rule.max_months):
            running[p.deal_id] = months[1]
    return lines
