#!/usr/bin/env python3
"""Evaluation workflow for Buy or Wait?.

Runs the engine against dataset/sample_requests.csv (which ships with the
organizer-provided expected output columns) and reports simple accuracy
metrics for the fields that have a clean categorical match, plus schema /
invariant checks against the full output.csv (0 <= amount_safe_to_pay <=
requested_amount, valid enum values, installment plans matching a supplied
option, etc.).

Usage:
    python3 code/evaluation/main.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pandas as pd
from engine import Data
from decide import Decision

_here = os.path.dirname(os.path.abspath(__file__))
ROOT = None
for cand in [os.path.dirname(_here), os.path.dirname(os.path.dirname(_here)), _here]:
    if os.path.exists(os.path.join(cand, "dataset")):
        ROOT = cand
        break
if ROOT is None:
    ROOT = os.path.dirname(_here)
DATA_DIR = os.path.join(ROOT, "dataset")

VALID_STATUS = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
VALID_METHOD = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}


def eval_samples(data):
    samples = pd.read_csv(os.path.join(DATA_DIR, "sample_requests.csv"))
    n = len(samples)
    status_correct = 0
    method_correct = 0
    amount_within_10pct = 0
    rows = []
    for _, req in samples.iterrows():
        dec = Decision(data, req)
        r = dec.decide()
        rows.append((req["request_id"], req["affordability_status"], r["affordability_status"],
                      req["recommended_payment_method"], r["recommended_payment_method"]))
        if r["affordability_status"] == req["affordability_status"]:
            status_correct += 1
        if r["recommended_payment_method"] == req["recommended_payment_method"]:
            method_correct += 1
        exp_amt = float(req["amount_safe_to_pay"])
        got_amt = float(r["amount_safe_to_pay"])
        denom = max(exp_amt, 1.0)
        if abs(exp_amt - got_amt) / denom <= 0.10:
            amount_within_10pct += 1

    print("=== sample_requests.csv (n=%d) ===" % n)
    print(f"affordability_status accuracy: {status_correct}/{n} = {status_correct/n:.2%}")
    print(f"recommended_payment_method accuracy: {method_correct}/{n} = {method_correct/n:.2%}")
    print(f"amount_safe_to_pay within 10%%: {amount_within_10pct}/{n} = {amount_within_10pct/n:.2%}")
    print()
    print("request_id | expected_status -> got_status | expected_method -> got_method")
    for rid, es, gs, em, gm in rows:
        flag = "" if (es == gs and em == gm) else "  <-- mismatch"
        print(f"{rid}: {es} -> {gs} | {em} -> {gm}{flag}")


def validate_output():
    out_path = os.path.join(ROOT, "output.csv")
    if not os.path.exists(out_path):
        print("\noutput.csv not found at repo root; run code/main.py first.")
        return
    out = pd.read_csv(out_path)
    requests = pd.read_csv(os.path.join(DATA_DIR, "requests.csv"))
    opts = pd.read_csv(os.path.join(DATA_DIR, "request_payment_options.csv"))

    print("\n=== output.csv validation ===")
    print(f"rows: {len(out)} (expected {len(requests)})")

    merged = out.merge(requests[["request_id", "requested_amount"]], on="request_id", how="left")
    bad_bounds = merged[
        (merged["amount_safe_to_pay"] < -1e-6) | (merged["amount_safe_to_pay"] > merged["requested_amount"] + 1e-6)
    ]
    print(f"amount_safe_to_pay out of [0, requested_amount]: {len(bad_bounds)}")

    bad_status = out[~out["affordability_status"].isin(VALID_STATUS)]
    bad_method = out[~out["recommended_payment_method"].isin(VALID_METHOD)]
    print(f"invalid affordability_status values: {len(bad_status)}")
    print(f"invalid recommended_payment_method values: {len(bad_method)}")

    # installment plans must match a supplied option's payment schedule exactly
    bad_installments = 0
    for _, row in out[out["recommended_payment_method"] == "installments"].iterrows():
        req_opts = opts[opts["request_id"] == row["request_id"]]
        req_opts = req_opts[req_opts["payment_method"] == "installments"]
        plan = row["payment_plan"]
        matched = False
        for _, o in req_opts.iterrows():
            n = int(o["number_of_payments"])
            expected_first = f"{o['first_payment_date']}:"
            if plan.startswith(expected_first) and plan.count("|") == n - 1:
                matched = True
                break
        if not matched:
            bad_installments += 1
    print(f"installment plans not matching a supplied option: {bad_installments}")

    missing_ids = set(requests["request_id"]) - set(out["request_id"])
    print(f"missing request_ids in output: {len(missing_ids)}")


if __name__ == "__main__":
    data = Data(DATA_DIR)
    eval_samples(data)
    validate_output()
