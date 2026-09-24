"""Tests for the web routes: the page and the JSON view render the real data.

The payment fetch is replaced by a fixed result, and the rule reading by the
hand-written rules, so neither the mock server nor Gemini is needed.
"""

import pytest
from fastapi.testclient import TestClient

import calculator.pipeline
from calculator.app import app
from calculator.commission import months_already
from calculator.data import DataIssue, load_inputs
from calculator.models import Payment
from calculator.payments import FetchError, FetchResult, FetchStats, PaymentError, fetch_payments
from calculator.reference_rules import reference_rule
from calculator.rules import RulesResult

client = TestClient(app)

FETCHED = FetchResult(
    payments=[Payment(deal_id="D01", payment_id="D01_p06", payment_date="2026-06-01",
                      amount=300, payment_term="mensual", currency="USD")],
    errors=[PaymentError("D09_x", "D09", "payment_term: bad")],
    stats=FetchStats(pages=1, retries=2),
)


@pytest.fixture(autouse=True)
def fake_fetch(monkeypatch):
    monkeypatch.setattr(calculator.pipeline, "fetch_payments", lambda: FETCHED)


class _Calls(list):
    """Each call's ``refresh``; ``temperatures`` has the temperature each one asked for."""

    def __init__(self):
        super().__init__()
        self.temperatures: list[float | None] = []


@pytest.fixture(autouse=True)
def fake_rules(monkeypatch):
    """Hand-written rules instead of Gemini; records each call."""
    calls = _Calls()

    def read(deals, *, refresh=False, temperature=None):
        calls.append(refresh)
        calls.temperatures.append(temperature)
        return RulesResult({d.deal_id: reference_rule(d) for d in deals}, "fake-model",
                           temperature=0.0 if temperature is None else temperature)
    monkeypatch.setattr(calculator.pipeline, "read_rules", read)
    return calls


def test_index_shows_all_deals():
    response = client.get("/")
    assert response.status_code == 200
    assert "Deals — hubspot_deals.csv (8)" in response.text
    assert "Pagos aprobados — pagos_aprobados.csv (30)" in response.text
    assert "Problemas en los datos" not in response.text  # the real files are clean
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
    months = months_already(data.approved, data.blocked_deals)
    assert months[first.deal_id] is None
    assert all(v is not None for k, v in months.items() if k != first.deal_id)


def test_index_shows_fetched_payments_and_errors():
    text = client.get("/").text
    assert "Pagos obtenidos de la API (1)" in text and "<td>D01_p06</td>" in text
    assert "requests reintentados (429 o error de red): 2" in text
    assert "Pagos con errores (1)" in text and "<td>D09_x</td>" in text


def test_failed_fetch_is_shown_and_inputs_still_render(monkeypatch):
    def fail():
        raise FetchError("gave up after 8 attempts")
    monkeypatch.setattr(calculator.pipeline, "fetch_payments", fail)
    response = client.get("/")
    assert response.status_code == 200
    assert "No se pudieron obtener los pagos" in response.text
    assert "gave up after 8 attempts" in response.text
    assert "Deals — hubspot_deals.csv (8)" in response.text
    assert client.get("/api/data").json()["fetch_error"] == "gave up after 8 attempts"


def test_missing_payments_url_is_shown(monkeypatch):
    # The real fetch_payments; undo() would also revert conftest's DATA_DIR cleanup.
    monkeypatch.setattr(calculator.pipeline, "fetch_payments", fetch_payments)
    monkeypatch.delenv("PAYMENTS_API_URL", raising=False)
    text = client.get("/").text
    assert "No se pudieron obtener los pagos" in text and "PAYMENTS_API_URL is not set" in text


def test_index_shows_commission_lines():
    text = client.get("/").text
    assert "Líneas de comisión (2)" in text  # D01_p06 and the payment error
    assert "Cliente Andes - comision pago m6-m6 - restan 6" in text
    lines = client.get("/api/data").json()["lines"]
    assert lines[1]["payment_id"] == "D01_p06" and lines[1]["monto_a_comisionar"] == "63.00"


def test_page_says_which_model_read_the_rules():
    assert "Reglas leídas por fake-model" in client.get("/").text
    assert client.get("/api/data").json()["rules_model"] == "fake-model"


def test_buttons_recalculate_or_reread(fake_rules):
    text = client.get("/").text
    assert "Recalcular" in text and "Releer" not in text
    client.get("/")
    client.get("/?recalcular=1")
    client.get("/api/data?recalcular=1")
    assert fake_rules == [False, False, True, True]


def test_rules_error_is_shown(monkeypatch):
    def read(deals, *, refresh=False, temperature=None):
        return RulesResult({}, "fake-model", "GEMINI_API_KEY is not set")
    monkeypatch.setattr(calculator.pipeline, "read_rules", read)
    text = client.get("/").text
    assert "No se pudieron leer las reglas" in text and "GEMINI_API_KEY is not set" in text
    assert client.get("/api/data").json()["rules_error"] == "GEMINI_API_KEY is not set"


def test_no_rules_read_when_the_fetch_fails(monkeypatch, fake_rules):
    def fail():
        raise FetchError("down")
    monkeypatch.setattr(calculator.pipeline, "fetch_payments", fail)
    client.get("/")
    assert fake_rules == []


def test_partners_page_groups_lines_into_transfers():
    response = client.get("/partners")
    assert response.status_code == 200
    assert "Partner Sur · USD 63.00" in response.text
    assert "Partner Sur - 1 comision - total 63.00: Cliente Andes - comision pago m6-m6 - restan 6" in response.text


def test_commissions_json():
    body = client.get("/api/commissions").json()
    assert body["rules_model"] == "fake-model" and body["fetch_error"] is None
    assert [t["partner"] for t in body["transfers"]] == ["Partner Sur"]
    d01 = body["rules"]["D01"]
    assert d01["source_text"].startswith("partner_commission_pct: 25% - 12 meses")
    assert d01["rule"]["tiers"][0]["pct"] == "25"


def test_rules_section_shows_every_step(monkeypatch, fake_rules):
    text = client.get("/").text
    assert "Reglas leídas (8)" in text
    assert 'id="regla-D04"' in text and "el texto menciona un partner fee incompleto" in text
    assert '<a href="#regla-D01">D01</a>' in text  # a line links to its rule


def test_missing_input_file_is_shown(monkeypatch, fake_rules):
    def broken(folder):
        raise calculator.pipeline.DataError("hubspot_deals.csv: file not found at /x")
    monkeypatch.setattr(calculator.pipeline, "load_inputs", broken)
    response = client.get("/")
    assert response.status_code == 200
    assert "No se pudieron cargar los archivos de entrada" in response.text and "file not found" in response.text
    assert client.get("/partners").status_code == 200
    assert client.get("/api/commissions").json()["load_error"].startswith("hubspot_deals.csv")
    assert fake_rules == []


def test_commissions_csv_matches_the_expected_output_format():
    from pathlib import Path
    response = client.get("/api/commissions.csv")
    assert response.headers["content-type"].startswith("text/csv")
    rows = response.text.splitlines()
    expected = (Path(__file__).parent / "fixtures" / "expected_output_PUBLIC.csv").read_text().splitlines()
    assert rows[0] == expected[0]  # same columns, same order
    assert expected[1] in rows  # D01_p06, written exactly as the expected output writes it
    assert "D09,D09_x,,,,0,requiere_revision," in rows  # a line in review: blanks, amount 0


def test_data_dir_setting_swaps_the_input_files(monkeypatch, tmp_path):
    # A folder with only D01 and its history: the page must use it, and say so.
    import shutil
    from calculator.data import DATA_DIR
    for name in ("hubspot_deals.csv", "pagos_aprobados.csv"):
        rows = (DATA_DIR / name).read_text().splitlines()
        (tmp_path / name).write_text("\n".join([rows[0]] + [r for r in rows[1:] if r.startswith("D01,")]) + "\n")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    text = client.get("/").text
    assert "configurado con <code>DATA_DIR</code>" in text and str(tmp_path) in text
    assert "Deals — hubspot_deals.csv (1)" in text
    assert client.get("/api/commissions").json()["data_dir"] == str(tmp_path)


def test_missing_data_dir_is_shown(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "no_existe"))
    text = client.get("/").text
    assert "No se pudieron cargar los archivos de entrada" in text and "no_existe" in text


def test_default_data_is_not_announced(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    assert "configurado con" not in client.get("/").text


def test_temperature_from_the_page(fake_rules, monkeypatch):
    monkeypatch.delenv("GEMINI_TEMPERATURE", raising=False)
    text = client.get("/").text
    assert 'name="temperatura"' in text and 'value="0"' in text  # the setting's value
    assert "Reglas leídas por fake-model (temperatura del LLM: 0)." in text
    text = client.get("/?recalcular=1&temperatura=0.7").text
    assert fake_rules.temperatures == [None, 0.7]
    assert 'value="0.7"' in text and "(temperatura del LLM: 0.7)." in text
    assert 'href="/partners?temperatura=0.7"' in text  # kept when changing pages
    assert client.get("/api/data?temperatura=0.7").json()["rules_temperature"] == 0.7


def test_form_starts_at_the_setting(monkeypatch):
    monkeypatch.setenv("GEMINI_TEMPERATURE", "1.2")
    assert 'value="1.2"' in client.get("/").text
    assert 'href="/partners"' in client.get("/").text  # nothing chosen, nothing kept


@pytest.mark.parametrize("value", ["-1", "2.1", "abc", ""])
def test_invalid_temperature_in_the_url_is_rejected(fake_rules, value):
    assert client.get(f"/?temperatura={value}").status_code == 422
    assert fake_rules == []
