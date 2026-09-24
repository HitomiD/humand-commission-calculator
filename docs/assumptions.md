# Assumptions and decisions

The choices that affect the results, and why. Where the data settles a question, the evidence is given; the rest are assumptions to confirm with the business.

## Months

- **Months are counted in sequence; dates are ignored.** A new payment covers the months right after those already commissioned (`sum(meses_cubiertos) + 1` onward). Evidence: `D01_p06` is dated 13 months after `D01`'s fifth payment, yet the expected output says `m6`; `D05` and `D06` behave the same. `date_of_first_payment` can't be the anchor: some are later than payments that already happened. So `D02_p13`, dated two years after `D02`'s annual payment, still covers `m13`.
- **A payment covers the months of its term:** mensual 1, trimestral 3, semestral 6, anual 12. Any other term is an error for that payment.
- **A payment covering more months than the rule has left is cut at the rule's end**, and only the remaining months are paid (`D06`: m9–m12 of a 6-month payment, `completo`).
- **"Año 1" / "1er año" with no later tier means 12 months at most** (`D06` ends at m12). "Perpetuo" and "año 2 en adelante" have no end.
- **Several new payments of one deal are taken in the order the API serves them**, each continuing from the previous one, so no month is paid twice. The current data never has two new payments for one deal.

## Base and amounts

- **The base comes from `commission_on_expansion`, never from the text.** `No`: the contract amount, whatever was paid (`D01` paid 300 on a 252 contract; the base is 252). `Yes`: the payment spread over its months (`D05`: 8664 / 12 = 722).
- **A payment below the contract amount is treated as a mistake**, on either base: the line goes to review and nothing is paid. The brief covers paying more ("aunque exceda contrato"), not less. No current payment triggers it.
- **A payment spanning two tiers is priced month by month** at each month's percentage (`D05`: 8 months at 50% + 4 at 30%).
- **Amounts are rounded once, at the end**, to cents, half up.

## Status

- `completo`: no months left after this payment. `incompleto`: months left. `en_curso`: the rule has no end.
- `no_corresponde` (our addition): nothing to pay, amount 0 and no memo. Used for "NO PAGAR" and for a payment arriving after the rule's months are used up (`D08`: 12 of 12 done when `D08_p13` arrives).
- **"NO PAGAR" still uses up the months** (`D03`): the notes say to update the sheet but not pay, so the payment is recorded and a later one starts after it.
- `requiere_revision`: anything that can't be computed with certainty. It's shown with its reason, never dropped. A deal's later payments also wait, since their months would be a guess.

## Reading the rule with the LLM

- **Gemini only sees `partner_commission_pct` and `partner_commission_notes`**, with no amounts or names, and fills a fixed schema at temperature 0. Validation in code decides whether the rule can be used.
- **A datum the text doesn't give is never filled in.** The model leaves the field empty and explains in a flag; any flag or failed check sends the deal to review. There is no confidence score: a model's rating of its own certainty isn't reliable.
- **The commission is counted in months, not payments**, and every tier needs a duration. "15% mensual" (no duration) and rules defined by payments go to review.
- **Thresholds and several partners** are detected and sent to review, not calculated.
- **Evaluation:** 80 texts (the 8 real deals and 72 invented ones), 3 runs each. 77 are right in every run and 1 is always sent to review (safe). The 2 misses are self-contradictory texts the model sometimes resolves instead of flagging.

## Partner fee (`D04`) — the main judgement call

`D04`: "Hay que ir descontando de los pagos de las comisiones hasta cubrir ese monto" (1,500 USD). **Our reading: the text says until when to deduct, not how much from each commission, so any amount per payment would be a guess and the line goes to review.** A fee is only calculated when the text gives the total and a fixed amount or percentage per payment.

The alternative reading is "take each commission whole until the fee is covered". It would pay `D04_p01` 3,600 − 1,500 = **2,100**, `en_curso`. It's a plausible business reading. We chose review because it's money going out and the text doesn't say it.

Also: for a deal with approved history, nothing records how much fee the manual process already deducted, so a fee on such a deal goes to review. When a capped rule ends with fee still owed, that last line goes to review: how to collect the rest is a business decision.

## Data and payments

- **A bad CSV row blocks only its deal**, whose payments go to review. A missing file or column stops the run and is shown on the page.
- **A payment served twice counts once**; if the two copies differ, it goes to review.
- **"Already paid" means the `payment_id` is in `pagos_aprobados.csv`.** `estado_pago_comision` and `date_of_first_payment` are informational only.

## Not done, and what production would need

- **Not done:** calculating threshold and multi-partner rules, and loading the config from the UI.
- **Possible improvement:** read each rule several times and use it only if the readings agree (catches the contradictory texts above), possibly with a moderate temperature, so ambiguity shows up as disagreement. To be measured with the evaluation set.
- **For production:** persistence of approved lines and of the rule used for each (today every run recomputes from the inputs), a human approval step writing back to the approved-payments record, and an audit log.
