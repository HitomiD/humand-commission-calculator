"""Tests for the web routes: the page and the JSON view render the real data.

The payment fetch is replaced by a fixed result, so no mock server is needed.
"""

import pytest
from fastapi.testclient import TestClient

import calculator.app
from calculator.app import _months_done, app
from calculator.data import DataIssue, load_inputs
from calculator.models import Payment
from calculator.payments import FetchError, FetchResult, FetchStats, PaymentError

client = TestClient(app)

FETCHED = FetchResult(
    payments=[Payment(deal_id="D01", payment_id="D01_p06", payment_date="2026-06-01",
                      amount=300, payment_term="mensual", currency="USD")],
    errors=[PaymentError("D09_x", "D09", "payment_term: bad")],
    stats=FetchStats(pages=1, retries=2),
)


@pytest.fixture(autouse=True)
def fake_fetch(monkeypatch):
    monkeypatch.setattr(calculator.app, "fetch_payments", lambda: FETCHED)


def test_index_shows_all_deals():
    response = client.get("/")
    assert response.status_code == 200
    assert "Deals (8)" in response.text
    assert "Approved payments (30)" in response.text
    assert "Data issues" not in response.text  # the real files are clean
    for n in range(1, 9):
        assert f"<td>D0{n}</td>" in response.text


def test_data_json():
    body = client.get("/api/data").json()
    assert len(body["deals"]) == 8
    assert len(body["approved_payments"]) == 30
    assert body["issues"] == [] and body["blocked_deals"] == []


def test_months_done_skips_blocked_deals():
    data = load_inputs()
    first = data.approved[0]
    # A duplicated payment_id must not double the months; the deal is blocked.
    data.approved.append(first)
    data.issues.append(DataIssue("pagos_aprobados.csv", 99, first.deal_id, "duplicate"))
    months = _months_done(data)
    assert months[first.deal_id] is None
    assert all(v is not None for k, v in months.items() if k != first.deal_id)


def test_index_shows_fetched_payments_and_errors():
    text = client.get("/").text
    assert "Fetched payments (1)" in text and "<td>D01_p06</td>" in text
    assert "requests retried (429 or network error): 2" in text
    assert "Payment errors (1)" in text and "<td>D09_x</td>" in text


def test_failed_fetch_is_shown_and_inputs_still_render(monkeypatch):
    def fail():
        raise FetchError("gave up after 8 attempts")
    monkeypatch.setattr(calculator.app, "fetch_payments", fail)
    response = client.get("/")
    assert response.status_code == 200
    assert "Payments could not be fetched" in response.text
    assert "gave up after 8 attempts" in response.text
    assert "Deals (8)" in response.text
    assert client.get("/api/data").json()["fetch_error"] == "gave up after 8 attempts"


def test_missing_payments_url_is_shown(monkeypatch):
    monkeypatch.undo()  # use the real fetch_payments
    monkeypatch.delenv("PAYMENTS_API_URL", raising=False)
    text = client.get("/").text
    assert "Payments could not be fetched" in text and "PAYMENTS_API_URL is not set" in text


def test_index_shows_commission_lines():
    text = client.get("/").text
    assert "Commission lines (2)" in text  # D01_p06 and the payment error
    assert "Cliente Andes - comision pago m6-m6 - restan 6" in text
    lines = client.get("/api/data").json()["lines"]
    assert lines[1]["payment_id"] == "D01_p06" and lines[1]["monto_a_comisionar"] == "63.00"
