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

## Edge cases the calculation handles

Every case below is covered by a test. When the system can't calculate a payment with certainty, the line is still shown, marked `requiere_revision`, with the reason and no amount paid.

| Case | What the system does |
|---|---|
| A payment covers more months than the rule has left (D06: 6 months, 4 left) | Commissions only the remaining months (m9–m12) and marks the deal `completo` |
| One payment spans two tiers (D05: m5–m16 across "50% year 1 / 30% year 2+") | Prices each month at its own tier: 8 × 50% + 4 × 30% |
| A payment arrives after the rule's months are used up (D08: 12 of 12) | `no_corresponde`, amount 0 |
| The deal's notes say not to pay (D03: "NO PAGAR") | Records the months but pays nothing |
| Several new payments for the same deal | Numbers the months in order, so no month is paid twice |
| The client pays less than the contract amount | Treated as a payment anomaly and sent to review |
| A partner fee with no stated way to deduct it (D04: "ir descontando") | Sent to review instead of guessing an amount per payment |
| A partner fee still owed when the rule's months run out | The last line goes to review, showing the gross amount, the deduction and the balance still owed |
| A later payment of a deal whose earlier payment is in review | Also sent to review, since its month numbering would be a guess |

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
