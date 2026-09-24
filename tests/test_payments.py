"""Tests for the paginated payment fetch, against a fake endpoint (no network)."""

import httpx
import pytest

from calculator.payments import MAX_ATTEMPTS, FetchError, fetch_all_payments


def _payment(n: int, deal: str = "D01", **changes) -> dict:
    return {
        "deal_id": deal,
        "payment_id": f"{deal}_m{n}",
        "payment_date": "2025-01-01",
        "amount": 252,
        "payment_term": "mensual",
        "currency": "USD",
    } | changes


class FakeMock:
    """Serves ``items`` like the mock does: cursor pages, plus scripted failures.

    ``fail`` lists what to answer before each successful response, in order:
    429 for a rate limit, "net" for a connection error. An unknown cursor
    restarts from the first item, exactly like the real mock.
    """

    def __init__(self, items: list, page_size: int = 3, fail: list | None = None):
        self.items, self.page_size, self.fail = items, page_size, list(fail or [])
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.fail:
            kind = self.fail.pop(0)
            if kind == "net":
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": {}})
        after = request.url.params.get("starting_after")
        ids = [i.get("payment_id") for i in self.items]
        start = ids.index(after) + 1 if after and after in ids else 0
        data = self.items[start:start + self.page_size]
        return httpx.Response(200, json={"object": "list", "data": data,
                                         "has_more": start + self.page_size < len(self.items)})


def _fetch(mock, sleeps: list | None = None):
    client = httpx.Client(base_url="http://mock", transport=httpx.MockTransport(mock))
    return fetch_all_payments(client, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_follows_pages_through_rate_limits():
    items = [_payment(n) for n in range(1, 11)]
    sleeps = []
    result = _fetch(FakeMock(items, page_size=3, fail=[429, 429, "net", 429]), sleeps)
    assert [p.payment_id for p in result.payments] == [i["payment_id"] for i in items]
    assert result.errors == []
    assert result.stats.pages == 4 and result.stats.retries == 4
    assert sleeps == [2.0, 2.0, 2.0, 2.0]


def test_gives_up_after_max_attempts():
    mock = FakeMock([_payment(1)], fail=[429] * MAX_ATTEMPTS)
    with pytest.raises(FetchError, match="gave up"):
        _fetch(mock)
    assert mock.requests == MAX_ATTEMPTS


def test_other_http_errors_stop_immediately():
    client = httpx.Client(base_url="http://mock",
                          transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(FetchError, match="HTTP 500"):
        fetch_all_payments(client, sleep=lambda s: None)


def test_identical_duplicate_is_kept_once():
    items = [_payment(1), _payment(2), _payment(1)]
    result = _fetch(FakeMock(items, page_size=10))
    assert [p.payment_id for p in result.payments] == ["D01_m1", "D01_m2"]
    assert result.errors == []


def test_conflicting_duplicate_is_an_error_and_not_used():
    items = [_payment(1), _payment(2), _payment(1, amount=999)]
    result = _fetch(FakeMock(items, page_size=10))
    assert [p.payment_id for p in result.payments] == ["D01_m2"]
    assert [(e.payment_id, e.deal_id) for e in result.errors] == [("D01_m1", "D01")]


def test_bad_payment_is_an_error_and_the_rest_continue():
    items = [_payment(1), _payment(2, payment_term="bimestral"), {"deal_id": "D02"}, _payment(3)]
    result = _fetch(FakeMock(items, page_size=2))
    assert [p.payment_id for p in result.payments] == ["D01_m1", "D01_m3"]
    assert {(e.payment_id, e.deal_id) for e in result.errors} == {("D01_m2", "D01"), (None, "D02")}


def test_pagination_that_does_not_advance_stops():
    # The page ends on an item without an id the mock recognises, so the next
    # request restarts from the first page: it must not loop forever.
    class Restarting(FakeMock):
        def __call__(self, request):
            return httpx.Response(200, json={"data": self.items, "has_more": True})

    with pytest.raises(FetchError, match="not advancing"):
        _fetch(Restarting([_payment(1), _payment(2)]))
