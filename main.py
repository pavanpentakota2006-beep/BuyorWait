#!/usr/bin/env python3
"""Buy or Wait? - main entry point.

Usage:
    python3 code/main.py

Reads dataset/requests.csv (and all supporting dataset/*.csv + dataset/media/images),
and writes <repo_root>/output.csv with one prediction row per request.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from engine import Data
from decide import Decision

_here = os.path.dirname(os.path.abspath(__file__))
ROOT = _here if os.path.exists(os.path.join(_here, "dataset")) else os.path.dirname(_here)
DATA_DIR = os.path.join(ROOT, "dataset")
OUT_PATH = os.path.join(ROOT, "output.csv")

COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def main():
    data = Data(DATA_DIR)
    requests = pd.read_csv(os.path.join(DATA_DIR, "requests.csv"))

    rows = []
    for _, req in requests.iterrows():
        try:
            dec = Decision(data, req)
            rows.append(dec.decide())
        except Exception as e:
            traceback.print_exc()
            rows.append(
                {
                    "request_id": req["request_id"],
                    "amount_safe_to_pay": 0,
                    "affordability_status": "not_affordable",
                    "recommended_payment_method": "not_recommended",
                    "payment_plan": "none",
                    "earliest_date_for_full_payment": "",
                    "spending_changes_needed": "none",
                    "decision_explanation": f"Could not evaluate this request due to an internal error ({e}).",
                }
            )

    out = pd.DataFrame(rows, columns=COLUMNS)
    out.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(out)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
