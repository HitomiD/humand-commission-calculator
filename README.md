# Commission calculator

Calculates the commission owed to a partner for each client payment not yet in `pagos_aprobados.csv`. An LLM (Gemini) reads each deal's free-text rule; the rest is plain, tested Python.

**Deployed:** https://humand-commission-calculator.vercel.app/ · `/partners` one transfer per partner · `/api/commissions` JSON with each line's full trace · `/api/commissions.csv` the same lines in the exact format of `expected_output_PUBLIC.csv`

The assumptions behind the results, with the evidence for each, are in [docs/assumptions.md](docs/assumptions.md).

## Run it locally

Needs Python 3 and Node. `./run_local.sh` sets up `.venv` and `.env`, and starts the payments mock (:4000) and the app (http://localhost:8000); Ctrl+C stops both. By hand:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # app + pytest
cp .env.example .env                       # then set GEMINI_API_KEY
node mock-api/dev-server.cjs               # terminal 1: payments mock
uvicorn api.index:app --reload --port 8000 # terminal 2: the app
pytest                                     # offline tests; Gemini is faked
python -m tests.eval_rules --runs 3        # optional: real Gemini on 80 rule texts
```

## Where to set the API key

In `.env` locally (git-ignored), or in the Vercel project's environment variables.

| Variable | Required | |
|---|---|---|
| `GEMINI_API_KEY` | yes | The LLM key |
| `PAYMENTS_API_URL` | yes | Payments endpoint, e.g. `http://localhost:4000/api/stripe/payments` |
| `GEMINI_MODEL` | no | Default `gemini-2.5-flash` |
| `GEMINI_TEMPERATURE` | no | 0–2, default 0; the page's "Temperatura" field overrides it for one run |
| `DATA_DIR` | no | A folder with your own two CSVs; default `data/` |

A missing setting is shown on the page instead of crashing it.

## How the commission rule is modeled

- **The LLM only reads text.** Gemini gets `partner_commission_pct` and `partner_commission_notes` (no amounts or names) and fills a fixed JSON schema: tiers `{from_month, to_month | null, pct}`, `do_not_pay`, a complete partner fee, the base the text mentions, and `flags`. What the text doesn't state is left empty and flagged, never filled in.
- **Code validates it** into a `CommissionRule` (tiers from month 1 with no gaps, percentages 0–100, a mentioned fee complete, a mentioned base matching the data); any problem or flag sends the deal to review.
- **The base never comes from the LLM:** `commission_on_expansion` `No` = the contract amount; `Yes` = the payment divided by the months it covers.
- **Calculation:** months done = sum of `meses_cubiertos`; a payment covers the next N months of its term (dates ignored), cut at the rule's end; each month is priced at its tier; the amount is rounded once. Memo: `{cliente} - comision pago m{a}-m{b} - restan {N|sin_limite}`; `/partners` joins a partner's memos into one line per transfer.
- **When Gemini is called:** once per deal, in parallel, on every "Recalcular"; a page load reuses the readings the running instance holds in memory. Nothing is stored.

## Missing data and unreliable responses

Nothing is guessed or dropped: what can't be computed with certainty becomes a `requiere_revision` line with its reason and amount 0, and the rest of the run continues.

- **LLM:** a failed call, an invalid reply, a failed validation or a model flag sends that deal to review, with the model's explanation; the page shows each text sent, the raw reply and the rule used. Evaluated on 80 rule texts, 3 runs each: 77 right every time (details in `docs/assumptions.md`).
- **Data:** a bad CSV row blocks only the deals it affects; an invalid payment, or one below the contract amount, becomes a review line.
- **Audit trail:** every line carries its trace: the rule, the months before, the tier breakdown and the fee.

## Pagination, rate limits and not processing a payment twice

- **Pagination:** follows `starting_after` until `has_more` is false; a page with no new payment stops the fetch instead of looping.
- **Rate limits:** a 429 or network error is retried after `Retry-After`, up to 8 attempts per page. If a page still fails, no lines are computed, since a partial list would hide payments, and the page says why.
- **No double processing:** a `payment_id` already in `pagos_aprobados.csv` is skipped; a payment served twice counts once (differing copies go to review); several new payments of one deal get consecutive months. The tool only proposes lines for a person to approve, so running it twice gives the same lines, not two payments.
