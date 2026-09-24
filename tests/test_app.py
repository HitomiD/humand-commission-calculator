"""Tests for the web routes: the page and the JSON view render the real data."""

from fastapi.testclient import TestClient

from calculator.app import app

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
