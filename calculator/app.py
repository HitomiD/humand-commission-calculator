"""Calculator web application.

FastAPI app that runs the commission pipeline (``calculator/pipeline.py``)
and renders the results with Jinja templates. It is served locally by
Uvicorn and on Vercel through ``api/index.py``.

Every route runs the whole pipeline. ``releer=1`` makes Gemini read every
rule again instead of reusing the readings this instance remembers (D-40).
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from calculator import pipeline
from calculator.rules import describe_rule

# Resolved from this file, like DATA_DIR, so it works under Uvicorn and Vercel.
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["describe_rule"] = describe_rule
templates.env.filters["as_json"] = lambda model: model.model_dump_json(indent=2)

app = FastAPI(title="Commission calculator")


def _page(request: Request, name: str, releer: bool) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"r": pipeline.run(refresh=releer)})


@app.get("/", response_class=HTMLResponse)
def index(request: Request, releer: bool = False):
    """Commission lines, the rules read, and the inputs they came from."""
    return _page(request, "index.html", releer)


@app.get("/partners", response_class=HTMLResponse)
def partners(request: Request, releer: bool = False):
    """The same lines grouped into one transfer per partner (step 5 of the challenge)."""
    return _page(request, "partners.html", releer)


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
def commissions_json(releer: bool = False) -> dict:
    r = pipeline.run(refresh=releer)
    return {
        "load_error": r.load_error,
        "fetch_error": r.fetch_error,
        "rules_model": r.rules.model if r.rules else None,
        "rules_error": r.rules.error if r.rules else None,
        "lines": r.lines,
        "transfers": r.transfers,
        "rules": _rules_json(r),
    }


# Everything the run used, inputs included, for debugging.
@app.get("/api/data")
def data_json(releer: bool = False) -> dict:
    r = pipeline.run(refresh=releer)
    d = r.data
    return {
        "load_error": r.load_error,
        "fetch_error": r.fetch_error,
        "rules_model": r.rules.model if r.rules else None,
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
