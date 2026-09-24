"""Calculator web application.

FastAPI app that runs the commission pipeline and renders the results with
Jinja templates. It is served locally by Uvicorn and on Vercel through
``api/index.py``.

A single page grows with each phase of the implementation plan: it currently
shows the loaded inputs; fetched payments and commission lines come later.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from calculator.data import InputData, load_inputs

# Resolved from this file, like DATA_DIR, so it works under Uvicorn and Vercel.
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

app = FastAPI(title="Commission calculator")


def _months_done(data: InputData) -> dict[str, int | None]:
    # Temporary: shown on the page until phase 3 moves reconciliation into
    # commission.py. Sum of meses_cubiertos per deal, never a row count (D-04).
    # A blocked deal gets None: its approved rows can't be trusted (D-22).
    blocked = data.blocked_deals
    totals: dict[str, int | None] = {d: None for d in blocked}
    for a in data.approved:
        if a.deal_id not in blocked:
            totals[a.deal_id] = totals.get(a.deal_id, 0) + a.meses_cubiertos
    return totals


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    data = load_inputs()
    return templates.TemplateResponse(
        request, "index.html", {"data": data, "months_done": _months_done(data)}
    )


# Same data as JSON, for debugging and for comparing against the expected
# output. On Vercel this path is rewritten to this app (see vercel.json).
@app.get("/api/data")
def data_json() -> dict:
    data = load_inputs()
    return {
        "deals": data.deals,
        "approved_payments": data.approved,
        "issues": data.issues,
        "blocked_deals": sorted(data.blocked_deals),
    }
