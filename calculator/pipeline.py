"""The whole run, steps 1–7, in one place.

``run()`` loads the inputs, fetches the payments, reads the rules with
Gemini, computes the lines and groups them into one transfer per partner. A
problem never stops it: each step's failure is kept in the result, and the
steps that depend on it are skipped, so the page can show what went wrong
next to everything that could still be computed.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from calculator.commission import build_lines, months_already, round_money
from calculator.config import ConfigError
from calculator.data import DataError, InputData, load_inputs
from calculator.models import CommissionLine, PartnerTransfer
from calculator.payments import FetchError, FetchResult, fetch_payments
from calculator.rules import RulesResult, read_rules


@dataclass(frozen=True)
class PipelineResult:
    load_error: str | None = None  # a missing or unreadable CSV: nothing else runs
    data: InputData | None = None
    months_done: dict[str, int | None] | None = None
    fetch_error: str | None = None  # no lines without the full payment list (D-26)
    fetched: FetchResult | None = None
    rules: RulesResult | None = None
    lines: list[CommissionLine] | None = None
    transfers: list[PartnerTransfer] | None = None


def transfer_memo(partner: str, lines: list[CommissionLine], total: Decimal) -> str:
    """One memo for a transfer that pays several lines (D-42):
    ``Partner Sur - 2 comisiones - total 1185.00: <memo> | <memo>``."""
    count = f"{len(lines)} comision{'es' if len(lines) != 1 else ''}"
    return f"{partner} - {count} - total {total}: " + " | ".join(l.memo for l in lines)


def group_transfers(lines: list[CommissionLine]) -> list[PartnerTransfer]:
    """One transfer per partner, sorted by partner, lines by deal and payment.

    A line is paid when it has a memo. Lines in review are listed with their
    partner but not paid; lines with no partner (a deal not in the deals
    file, a payment error) belong to no transfer and show on the main page.
    """
    paid, pending = defaultdict(list), defaultdict(list)
    for line in lines:
        if line.partner is None:
            continue
        if line.memo is not None:
            paid[line.partner].append(line)
        elif line.estado == "requiere_revision":
            pending[line.partner].append(line)

    def order(ls):
        return sorted(ls, key=lambda l: (l.deal_id or "", l.payment_id or ""))

    transfers = []
    for partner in sorted(paid.keys() | pending.keys()):
        ls = order(paid[partner])
        total = round_money(sum((l.monto_a_comisionar for l in ls), Decimal(0)))
        transfers.append(PartnerTransfer(
            partner=partner, lines=tuple(ls), total=total,
            memo=transfer_memo(partner, ls, total) if ls else None,
            pending=tuple(order(pending[partner])),
        ))
    return transfers


def run(*, refresh: bool = False) -> PipelineResult:
    """Run every step. ``refresh`` makes Gemini read every rule again (D-40)."""
    try:
        data = load_inputs()
    except DataError as e:
        return PipelineResult(load_error=str(e))
    months_done = months_already(data.approved, data.blocked_deals)

    try:
        fetched = fetch_payments()
    except (ConfigError, FetchError) as e:
        return PipelineResult(data=data, months_done=months_done, fetch_error=str(e))

    # Gemini is only asked when there are lines to compute (D-37).
    rules = read_rules(data.deals, refresh=refresh)
    lines = build_lines(data, fetched, lambda deal: rules.rules.get(deal.deal_id))
    return PipelineResult(data=data, months_done=months_done, fetched=fetched, rules=rules,
                          lines=lines, transfers=group_transfers(lines))
