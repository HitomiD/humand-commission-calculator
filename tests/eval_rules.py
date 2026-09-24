"""Evaluation of the real Gemini readings against the hand-written rules.

Run on demand, not by pytest (it calls Gemini and needs GEMINI_API_KEY):

    python -m tests.eval_rules --runs 3

Each run reads every deal again, skipping the in-memory readings, and compares
each rule with ``reference_rule``. A deal is "ok" when the rule is exactly
the reference, "flagged" when it has issues (it would go to review, which is
the safe outcome), and "WRONG" when it differs from the reference without any
issue: a wrong amount that would be paid. The runs together show how stable
the readings are (D-37).
"""

import argparse
import sys

from calculator.data import load_inputs
from calculator.reference_rules import reference_rule
from calculator.rules import describe_rule, read_rules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    runs = parser.parse_args().runs

    deals = load_inputs().deals
    outcomes: dict[str, list[str]] = {d.deal_id: [] for d in deals}
    wrong = 0
    for n in range(1, runs + 1):
        result = read_rules(deals, refresh=True)
        print(f"\n== Run {n} ({result.model}) ==")
        if result.error:
            print(f"cannot read rules: {result.error}")
            return 2
        for deal in deals:
            got, want = result.rules[deal.deal_id], reference_rule(deal)
            if got == want:
                outcome = "ok"
            elif got.issues:
                outcome = "flagged"
            else:
                outcome, wrong = "WRONG", wrong + 1
            outcomes[deal.deal_id].append(outcome)
            print(f"{deal.deal_id} {outcome:8} {describe_rule(got)}")
            for issue in got.issues:
                print(f"    issue: {issue}")
            if outcome == "WRONG":
                print(f"    expected: {describe_rule(want)}")

    print("\n== Summary ==")
    for deal_id, results in outcomes.items():
        stable = "stable" if len(set(results)) == 1 else "UNSTABLE"
        print(f"{deal_id} {' '.join(results):40} {stable}")
    print(f"\n{wrong} wrong reading(s) that would have been paid.")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
