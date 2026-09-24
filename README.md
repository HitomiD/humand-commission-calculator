# Commission calculator

This repository holds a commission payment calculator engine for the Humand partner program. It serves as the technical challenge for the  "AI Process Builder" selection process.

The calculator and payment mock live in separate source directories. Vercel serves them as Python and Node functions in one project.

## Run the calculator locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
```

Open `http://localhost:8000/`. The initial calculator response is `{"message":"hello world from calculator"}`.

## Run the payment mock locally

In another terminal:

```bash
node mock-api/dev-server.cjs
```

The mock endpoint is `http://localhost:4000/api/stripe/payments`. It may return HTTP 429; retry after the `Retry-After` interval. The local server and Vercel function import the same handler from `mock-api/handler.cjs`.

## How bad input data is handled

The CSVs in `data/` are validated row by row when they are loaded. A problem with one deal never stops the others from being calculated. Every problem is listed at the top of the page and in `/api/data`.

| Problem | Result |
|---|---|
| A file is missing, lacks a column, or isn't UTF-8 | The run stops with a clear error |
| A malformed row (blank required field, invalid value, extra cells) or a duplicated `deal_id` / `payment_id` | That deal is **blocked**: its new payments go to manual review instead of being calculated |
| An approved-payment row with no `deal_id` | **Every** deal is blocked, because those months could belong to any of them |
| An approved row for an unknown deal, or a `payment_id` that doesn't start with `{deal_id}_` | Warning only; nothing is blocked |
