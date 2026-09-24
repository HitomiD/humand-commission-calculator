"""Calculator web application.

FastAPI app that runs the commission pipeline (``calculator/pipeline.py``)
and renders the results with Jinja templates. It is served locally by
Uvicorn and on Vercel through ``api/index.py``.

Every route runs the whole pipeline. ``recalcular=1`` (the "Recalcular"
button) makes Gemini read every rule again; a plain page load reuses the
readings this instance remembers (D-40). ``temperatura`` overrides
``GEMINI_TEMPERATURE`` for that request (D-48).
"""

import csv
import io
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from calculator import config, pipeline
from calculator.rules import describe_rule

# Resolved from this file, like DATA_DIR, so it works under Uvicorn and Vercel.
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["describe_rule"] = describe_rule
# Money is always shown with its currency; the challenge states all amounts are USD.
templates.env.filters["usd"] = lambda v: "" if v is None else f"USD {v}"
templates.env.filters["as_json"] = lambda model: model.model_dump_json(indent=2)
templates.env.filters["num"] = lambda x: f"{x:g}"  # 0.0 → 0, 0.5 → 0.5

app = FastAPI(title="Commission calculator")

# The temperature Gemini reads the rules at, for this request only (D-48).
Temperatura = Annotated[float | None, Query(ge=0, le=config.MAX_TEMPERATURE)]


def _default_temperature() -> float:
    """The setting, to fill the form; 0 when it's invalid (the page says so
    once the rules are read)."""
    try:
        return config.gemini_temperature()
    except config.ConfigError:
        return 0.0


def _page(request: Request, name: str, recalcular: bool, temperatura: float | None) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {
        "r": pipeline.run(refresh=recalcular, temperature=temperatura),
        "temperatura": temperatura,  # asked for in the URL: the links keep it
        "temperatura_form": _default_temperature() if temperatura is None else temperatura,
    })


@app.get("/", response_class=HTMLResponse)
def index(request: Request, recalcular: bool = False, temperatura: Temperatura = None):
    """Commission lines, the rules read, and the inputs they came from."""
    return _page(request, "index.html", recalcular, temperatura)


@app.get("/partners", response_class=HTMLResponse)
def partners(request: Request, recalcular: bool = False, temperatura: Temperatura = None):
    """The same lines grouped into one transfer per partner (step 5 of the challenge)."""
    return _page(request, "partners.html", recalcular, temperatura)


def _rules_json(r: pipeline.PipelineResult) -> dict | None:
    if r.rules is None:
        return None
    return {
        deal_id: {
            "source_text": rule.source_text,
            "reading": r.rules.readings.get(deal_id),  # what the model returned
            "rule": rule,  # after validation
        }
        for deal_id, rule in r.rules.rules.items()
    }


# The results as JSON, e.g. to compare with the expected output. On Vercel,
# every /api/* path is rewritten to this app (see vercel.json).
@app.get("/api/commissions")
def commissions_json(recalcular: bool = False, temperatura: Temperatura = None) -> dict:
    r = pipeline.run(refresh=recalcular, temperature=temperatura)
    return {
        "data_dir": r.data_dir,
        "load_error": r.load_error,
        "fetch_error": r.fetch_error,
        "rules_model": r.rules.model if r.rules else None,
        "rules_temperature": r.rules.temperature if r.rules else None,
        "rules_error": r.rules.error if r.rules else None,
        "lines": r.lines,
        "transfers": r.transfers,
        "rules": _rules_json(r),
    }


# The expected output's columns, in its order (tests/fixtures/expected_output_PUBLIC.csv).
EXPECTED_COLUMNS = ["deal_id", "payment_id", "base_usada", "base_mensual", "meses_elegibles",
                    "monto_a_comisionar", "estado", "memo"]


def _csv_value(value) -> str:
    """A cell as the expected output writes it: numbers without trailing
    zeros (63, 3754.4), blanks for missing values."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


# The lines in the exact format of the expected output, so they can be
# compared with it cell by cell. Lines in review are included, with blanks.
@app.get("/api/commissions.csv")
def commissions_csv(recalcular: bool = False, temperatura: Temperatura = None) -> PlainTextResponse:
    r = pipeline.run(refresh=recalcular, temperature=temperatura)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPECTED_COLUMNS)
    for line in r.lines or []:
        writer.writerow([_csv_value(getattr(line, c)) for c in EXPECTED_COLUMNS])
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="commissions.csv"'})


# Everything the run used, inputs included, for debugging.
@app.get("/api/data")
def data_json(recalcular: bool = False, temperatura: Temperatura = None) -> dict:
    r = pipeline.run(refresh=recalcular, temperature=temperatura)
    d = r.data
    return {
        "data_dir": r.data_dir,
        "load_error": r.load_error,
        "fetch_error": r.fetch_error,
        "rules_model": r.rules.model if r.rules else None,
        "rules_temperature": r.rules.temperature if r.rules else None,
        "rules_error": r.rules.error if r.rules else None,
        "lines": r.lines,
        "rules": _rules_json(r),
        "deals": d.deals if d else None,
        "approved_payments": d.approved if d else None,
        "issues": d.issues if d else None,
        "blocked_deals": sorted(d.blocked_deals) if d else None,
        "payments": r.fetched.payments if r.fetched else None,
        "payment_errors": r.fetched.errors if r.fetched else None,
        "fetch_stats": r.fetched.stats if r.fetched else None,
    }
