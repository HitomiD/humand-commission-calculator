"""Fetch every payment from the mock Stripe endpoint (pipeline step 2).

The endpoint is paginated with a ``starting_after`` cursor and answers a share
of requests with HTTP 429. This module follows the cursor to the end, waits
and retries on 429s and network errors, and returns the full set.

A bad payment never stops the run: it becomes a ``PaymentError`` and the rest
continue (decision D-20). Only a fetch that can't be completed raises
``FetchError``, because a partial list would hide new payments.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from pydantic import ValidationError

from calculator.config import payments_api_url
from calculator.models import Payment

PAGE_LIMIT = 100  # the mock's maximum
MAX_ATTEMPTS = 8  # per page, counting the first try
MAX_PAGES = 1000  # far above the data size; stops a cursor that never ends
DEFAULT_RETRY_AFTER = 2.0  # seconds, when the header is missing or invalid
MAX_RETRY_AFTER = 30.0  # never wait longer than this on one retry


class FetchError(Exception):
    """The payment list could not be fetched completely."""


@dataclass(frozen=True)
class PaymentError:
    """A fetched payment that can't be used; its deal goes to review."""

    payment_id: str | None
    deal_id: str | None
    message: str


@dataclass
class FetchStats:
    """Shown on the page so the retry handling is visible."""

    pages: int = 0  # successful page responses
    retries: int = 0  # requests repeated after a 429 or network error


@dataclass
class FetchResult:
    payments: list[Payment]  # valid, unique, in the order the API served them
    errors: list[PaymentError] = field(default_factory=list)
    stats: FetchStats = field(default_factory=FetchStats)


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return DEFAULT_RETRY_AFTER
    return min(max(seconds, 0.0), MAX_RETRY_AFTER)


def _get_page(client: httpx.Client, url: str, params: dict, stats: FetchStats, sleep: Callable[[float], None]) -> dict:
    """GET one page, retrying 429s and network errors up to ``MAX_ATTEMPTS``."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(url, params=params)
        except httpx.TransportError as e:
            problem, wait = f"network error: {e}", DEFAULT_RETRY_AFTER
        else:
            if response.status_code == 429:
                problem, wait = "rate limited (429)", _retry_after(response)
            elif response.is_success:
                try:
                    body = response.json()
                except ValueError as e:
                    raise FetchError(f"response is not JSON: {e}") from e
                if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                    raise FetchError("response has no 'data' list")
                stats.pages += 1
                return body
            else:
                raise FetchError(f"HTTP {response.status_code}: {response.text[:200]}")
        if attempt < MAX_ATTEMPTS:
            stats.retries += 1
            sleep(wait)
    raise FetchError(f"gave up after {MAX_ATTEMPTS} attempts; last problem: {problem}")


def fetch_all_payments(
    client: httpx.Client, url: str, sleep: Callable[[float], None] = time.sleep
) -> FetchResult:
    """Follow the cursor until ``has_more`` is false and return every payment.

    ``url`` is the full endpoint URL. ``sleep`` is replaceable so tests don't
    wait.
    """
    stats = FetchStats()
    raw: dict[str, dict] = {}  # first copy of each payment_id, in served order
    errors: list[PaymentError] = []
    conflicting: set[str] = set()
    cursor: str | None = None

    for _ in range(MAX_PAGES):
        params = {"limit": PAGE_LIMIT}
        if cursor:
            params["starting_after"] = cursor
        body = _get_page(client, url, params, stats, sleep)
        items = body["data"]

        new_ids = 0
        for item in items:
            pid = item.get("payment_id") if isinstance(item, dict) else None
            if not isinstance(pid, str) or not pid:
                errors.append(PaymentError(None, _deal_of(item), f"payment without a payment_id: {item!r}"))
                continue
            if pid not in raw:
                raw[pid] = item
                new_ids += 1
            elif raw[pid] != item and pid not in conflicting:
                # Two versions of one payment: using either would be a guess (D-27).
                conflicting.add(pid)
                errors.append(PaymentError(pid, _deal_of(item), "served twice with different content"))

        if not body.get("has_more"):
            break
        # The mock restarts from the first payment when it doesn't know the
        # cursor, so a page with nothing new would loop forever (D-26).
        if new_ids == 0:
            raise FetchError(f"page after {cursor!r} brought no new payments; pagination is not advancing")
        cursor = items[-1].get("payment_id") if isinstance(items[-1], dict) else None
        if not isinstance(cursor, str) or not cursor:
            raise FetchError("last item of a page has no payment_id to continue from")
    else:
        raise FetchError(f"more than {MAX_PAGES} pages; stopping")

    payments = []
    for pid, item in raw.items():
        if pid in conflicting:
            continue
        try:
            payments.append(Payment.model_validate(item))
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            errors.append(PaymentError(pid, _deal_of(item), problems))
    return FetchResult(payments, errors, stats)


def _deal_of(item) -> str | None:
    deal = item.get("deal_id") if isinstance(item, dict) else None
    return deal if isinstance(deal, str) and deal else None


def fetch_payments() -> FetchResult:
    """Fetch from ``PAYMENTS_API_URL``; raises ``ConfigError`` if it isn't set."""
    url = payments_api_url()
    with httpx.Client(timeout=10.0) as client:
        return fetch_all_payments(client, url)
