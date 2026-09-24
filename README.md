# Commission calculator

Calculates the commissions owed to partners for each new client payment. It reads the deals and the approved payments from CSV, fetches the payments from the Stripe-like API, has an LLM (Gemini) read each deal's free-text commission rule, and computes one line per new payment for a person to approve.

**Deployed:** `<deployment URL>` · `/` lines and the rules read · `/partners` one transfer per partner with a combined memo · `/api/commissions` the same as JSON

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # app + pytest
cp .env.example .env                       # then set GEMINI_API_KEY
node mock-api/dev-server.cjs               # terminal 1: payments mock on :4000
uvicorn api.index:app --reload --port 8000 # terminal 2: open http://localhost:8000
pytest                                     # tests; no network, Gemini is faked
python -m tests.eval_rules --runs 3        # optional: real Gemini readings vs the reference rules
```

## Where to set the API key

| Variable | Required | What it is |
|---|---|---|
| `GEMINI_API_KEY` | yes | The LLM key. Locally in `.env` (git-ignored); on Vercel in the project's environment variables |
| `PAYMENTS_API_URL` | yes | Full payments endpoint, e.g. `http://localhost:4000/api/stripe/payments` |
| `GEMINI_MODEL` | no | Defaults to `gemini-2.5-flash` |

A missing setting doesn't crash the page: it says what's missing. Without the payments URL nothing is computed; without the Gemini key every line goes to review.

## How the commission rule is modeled

The LLM only turns text into a rule. Everything after that is plain, tested Python.

1. **What the LLM sees:** only `partner_commission_pct` and `partner_commission_notes`, no amounts or names. It fills a JSON schema (structured output, temperature 0): tiers `{from_month, to_month | null, pct}`, `do_not_pay`, a partner `fee` (total and how it's deducted), the base the text mentions, and `flags` for anything ambiguous. The prompt is in Spanish, like the texts, and teaches the conventions with invented examples ("año 1" = months 1–12, "perpetuo" = no end).
2. **Validation** turns that into a `CommissionRule`: percentages 0–100, tiers starting at month 1 with no gaps or overlaps, a fee whose amount and mechanism agree, and a base that agrees with the data. Each problem, and each model flag, becomes an issue; a rule with issues is never used.
3. **The base is never taken from the LLM:** it comes from `commission_on_expansion` (`Yes`: the payment spread over its months; `No`: the contract amount). A base mentioned in the text is only a cross-check.
4. **Calculation:** months already commissioned = sum of `meses_cubiertos`; a new payment covers the next N months (N from `payment_term`, dates ignored); months past the rule's end are cut; each month is priced at its own tier; the amount is rounded once, to cents. `estado` is `completo`, `incompleto`, `en_curso` (no end), `no_corresponde` or `requiere_revision`.
5. **Memo:** each paid line gets `{cliente} - comision pago m{a}-m{b} - restan {N|sin_limite}`. When one transfer groups several deals of a partner (`/partners`), its memo is a single line that keeps every line's memo, so each amount can be matched: `Partner Sur - 2 comisiones - total 1185.00: Cliente Andes - comision pago m6-m6 - restan 6 | Cliente Fohn - comision pago m9-m12 - restan 0`. Lines in review are listed under the partner but not paid.

## Missing data and unreliable responses

Nothing is guessed silently and nothing is dropped: whatever can't be computed with certainty becomes a `requiere_revision` line with its reason and no amount, and the rest of the run goes on.

- **LLM:** a failed call (after the SDK's retries), an invalid reply, a rule that fails validation, or a model flag sends that deal to review, with the model's own explanation when it gave one. The page shows, per deal, the text sent, the model's raw reply and the rule used. Evaluated against hand-written reference rules: 8 of 8 deals correct in 3 runs out of 3.
- **CSV:** a malformed or duplicated row blocks only its deal; a missing file or column is shown as an error.
- **Payments:** an invalid payment (unknown term, other currency…) becomes a review line; the rest are used.
- **Calculation cases sent to review, not guessed:** a payment below the contract amount; a partner fee whose deduction per payment isn't stated; a fee still owed when the rule ends; later payments of a deal already in review. "NO PAGAR" records the months but pays 0.
- **Audit trail:** every line carries its trace (rule, months before, tier breakdown, fee), and every number traces back to its payment, deal and rule text.

## Pagination, rate limits and idempotency

- **Pagination:** follows `starting_after` with the last `payment_id` until `has_more` is false. A page that brings no new payment stops the fetch instead of looping, and 1000 pages is a hard cap.
- **Rate limits:** a 429 or network error is retried after `Retry-After` (capped), up to 8 attempts per page. If a page still fails, no lines are computed at all, since a partial list would hide payments; the page shows the error.
- **No double processing:**
  - a payment already in `pagos_aprobados.csv` (same `payment_id`) is never commissioned again;
  - a payment served twice counts once; if the two copies differ, it goes to review;
  - several new payments of one deal get consecutive months, never the same ones.

  Each run recomputes from the inputs and pays nothing itself: it proposes lines, a person approves them, and approved payments go into `pagos_aprobados.csv`. Running it twice gives the same lines, not two payments.
