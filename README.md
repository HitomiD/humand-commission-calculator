# Commission calculator

This repository holds a commission payment calculator engine for the Humand partner program. It serves as the technical challenge for the  "AI Process Builder" selection process.

The calculator and payment mock live in separate source directories. Vercel serves them as Python and Node functions in one project.

## Run the calculator locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PAYMENTS_API_URL=http://localhost:4000/api/stripe/payments
uvicorn api.index:app --reload --port 8000
```

`PAYMENTS_API_URL` is the full URL of the payments endpoint, and it is required. The calculator treats the payments API as an external service: point it at the local mock (below) or at any deployment, for example `https://<deployment>.vercel.app/api/stripe/payments`. On Vercel, set it in the project's environment variables. If it isn't set, the page says so instead of loading payments.

Open `http://localhost:8000/`. The initial calculator response is `{"message":"hello world from calculator"}`.

## Run the payment mock locally

In another terminal:

```bash
node mock-api/dev-server.cjs
```

The mock endpoint is `http://localhost:4000/api/stripe/payments`. It may return HTTP 429; retry after the `Retry-After` interval. The local server and Vercel function import the same handler from `mock-api/handler.cjs`.

## How bad input data is handled

The CSVs in `data/` are validated row by row when they are loaded. A problem with one deal never stops the others from being calculated. Every problem is listed at the top of the page and in `/api/data`.

**Both files**

| Problem | Result |
|---|---|
| A file is missing, lacks a column, or isn't UTF-8 | The run stops with a clear error |

**Deals (`hubspot_deals.csv`)**

| Problem | Result |
|---|---|
| A malformed row (blank required field, invalid value, extra cells) | The deal is **blocked** and left out of the deal list. Its new payments go to manual review |
| A duplicated `deal_id` | The same, for every copy |
| A blank `deal_id` | Reported, but there is no deal to block. A payment for a deal that isn't in the list will go to review too (planned, with the calculation) |

**Approved payments (`pagos_aprobados.csv`)**

| Problem | Result |
|---|---|
| A malformed row (blank required field, invalid value, extra cells) | The deal is **blocked**: its months already commissioned are unknown, so its new payments go to manual review |
| A duplicated `payment_id` | Every deal involved is blocked |
| A blank `deal_id` | **Every** deal is blocked, because those months could belong to any of them |
| A row for a deal that isn't in the deals file | Warning only |
| A `payment_id` that doesn't start with `{deal_id}_` | Warning only, for a person to check |

A blocked deal's approved rows are still loaded, so code that uses them must check the blocked list first.
