"""Calculator web application.

FastAPI app that runs the commission pipeline and renders the results with
Jinja templates. It is served locally by Uvicorn and on Vercel through
``api/index.py``.

A single page grows with each phase of the implementation plan: it currently
shows the commission lines, the fetched payments and the loaded inputs.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from calculator.commission import build_lines, months_already
from calculator.config import ConfigError
from calculator.data import InputData, load_inputs
from calculator.payments import FetchError, FetchResult, fetch_payments
from calculator.reference_rules import reference_rule

# Resolved from this file, like DATA_DIR, so it works under Uvicorn and Vercel.
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

app = FastAPI(title="Commission calculator")


def _months_done(data: InputData) -> dict[str, int | None]:
    return months_already(data.approved, data.blocked_deals)


def _lines(data: InputData, fetched: FetchResult | None):
    # No lines without the full payment list: a partial one would hide payments.
    # Rules are the hand-written ones until the LLM parser exists (phase 4).
    return build_lines(data, fetched, reference_rule) if fetched else None


def _fetch() -> tuple[FetchResult | None, str | None]:
    # A failed fetch is shown on the page instead of failing the request, so
    # the inputs and their issues stay visible (D-26).
    try:
        return fetch_payments(), None
    except (ConfigError, FetchError) as e:
        return None, str(e)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    data = load_inputs()
    fetched, fetch_error = _fetch()
    return templates.TemplateResponse(request, "index.html", {
        "data": data,
        "months_done": _months_done(data),
        "fetched": fetched,
        "fetch_error": fetch_error,
        "lines": _lines(data, fetched),
    })


# Same data as JSON, for debugging and for comparing against the expected
# output. On Vercel this path is rewritten to this app (see vercel.json).
@app.get("/api/data")
def data_json() -> dict:
    data = load_inputs()
    fetched, fetch_error = _fetch()
    return {
        "lines": _lines(data, fetched),
        "deals": data.deals,
        "approved_payments": data.approved,
        "issues": data.issues,
        "blocked_deals": sorted(data.blocked_deals),
        "payments": fetched.payments if fetched else None,
        "payment_errors": fetched.errors if fetched else None,
        "fetch_stats": fetched.stats if fetched else None,
        "fetch_error": fetch_error,
    }
