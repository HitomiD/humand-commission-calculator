"""Tests for the web routes: the page and the JSON view render the real data."""

from fastapi.testclient import TestClient

from calculator.app import _months_done, app
from calculator.data import DataIssue, load_inputs

client = TestClient(app)


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
