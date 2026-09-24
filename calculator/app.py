"""Calculator web application.

FastAPI app that will run the commission pipeline (fetch payments from the
mock, parse deal rules, compute commission lines) and render the results with
Jinja templates. It is served locally by Uvicorn and on Vercel through
``api/index.py``.
"""

from fastapi import FastAPI

app = FastAPI(title="Commission calculator")


# Placeholder route. On Vercel, "/" and "/api/*" are rewritten to this app
# (see vercel.json), so both paths are registered to confirm the routing works.
@app.get("/")
@app.get("/api")
def hello() -> dict[str, str]:
    return {"message": "hello world from calculator"}
