#!/usr/bin/env python3
"""
Buy or Wait? — Financial Affordability & Cash-Flow Intelligence Platform Server
Runs on port 5176 using Python Standard Library HTTP server with live decision intelligence.
"""

import csv
import datetime as dt
import json
import mimetypes
import os
import urllib.parse
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pandas as pd

from decide import Decision
from engine import Data, UserForecast, _parse_date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = HERE
DATA_DIR = os.path.join(ROOT_DIR, "dataset")
OUT_PATH = os.path.join(ROOT_DIR, "output.csv")
STATIC_DIR = os.path.join(ROOT_DIR, "static")


# Helper to read CSV files cleanly via standard library
def read_csv_records(file_path: str) -> list[dict[str, str]]:
    if not os.path.exists(file_path):
        return []
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


print("Loading Buy or Wait? financial engine data...")
engine_data = Data(DATA_DIR)
print(
    f"Loaded {len(engine_data.profiles)} profiles and "
    f"{len(engine_data.events)} historical/forecast events."
)

# Load datasets
raw_requests = read_csv_records(os.path.join(DATA_DIR, "requests.csv"))
raw_payment_options = read_csv_records(
    os.path.join(DATA_DIR, "request_payment_options.csv")
)
raw_profiles = read_csv_records(os.path.join(DATA_DIR, "financial_profiles.csv"))
raw_sample_requests = read_csv_records(os.path.join(DATA_DIR, "sample_requests.csv"))
raw_outputs = read_csv_records(OUT_PATH)

out_by_id = {r.get("request_id", ""): r for r in raw_outputs}
profiles_by_id = {r.get("user_id", ""): r for r in raw_profiles}
payment_options_by_req = defaultdict(list)
for opt in raw_payment_options:
    payment_options_by_req[opt.get("request_id", "")].append(opt)

# Pre-merge requests with output and profile data for instant browsing
merged_records = []
for req in raw_requests:
    rid = str(req.get("request_id", ""))
    uid = str(req.get("user_id", ""))
    out_info = out_by_id.get(rid, {})
    prof_info = profiles_by_id.get(uid, {})
    cur = str(prof_info.get("home_currency", "USD"))

    earliest_date_raw = out_info.get("earliest_date_for_full_payment")
    earliest_date = ""
    if earliest_date_raw is not None and str(earliest_date_raw) not in (
        "",
        "nan",
        "None",
    ):
        earliest_date = str(earliest_date_raw)

    max_inst_val = prof_info.get("max_installment_months")
    max_inst = None
    if max_inst_val is not None and str(max_inst_val) not in ("", "nan", "None"):
        try:
            max_inst = float(max_inst_val)
        except (ValueError, TypeError):
            max_inst = None

    try:
        req_amt = float(req.get("requested_amount", 0.0))
    except (ValueError, TypeError):
        req_amt = 0.0

    try:
        safe_amt = float(out_info.get("amount_safe_to_pay", 0.0))
    except (ValueError, TypeError):
        safe_amt = 0.0

    try:
        cur_bal = float(prof_info.get("current_available_balance", 0.0))
    except (ValueError, TypeError):
        cur_bal = 0.0

    try:
        min_bal = float(prof_info.get("minimum_balance_to_keep", 0.0))
    except (ValueError, TypeError):
        min_bal = 0.0

    merged_records.append(
        {
            "request_id": rid,
            "user_id": uid,
            "request_date": str(req.get("request_date", "")),
            "requested_amount": req_amt,
            "requested_currency": cur,
            "category": str(req.get("request_type", "General")),
            "item_description": str(req.get("request_text", "")),
            "desired_completion_date": str(req.get("desired_completion_date", "")),
            "allows_partial_payment": str(req.get("allows_partial_payment", "")).lower()
            in ("true", "1", "yes"),
            # Output prediction fields
            "amount_safe_to_pay": safe_amt,
            "affordability_status": str(
                out_info.get("affordability_status", "not_affordable")
            ),
            "recommended_payment_method": str(
                out_info.get("recommended_payment_method", "not_recommended")
            ),
            "payment_plan": str(out_info.get("payment_plan", "none")),
            "earliest_date_for_full_payment": earliest_date,
            "spending_changes_needed": str(
                out_info.get("spending_changes_needed", "none")
            ),
            "decision_explanation": str(out_info.get("decision_explanation", "")),
            # Profile summary
            "home_currency": cur,
            "current_available_balance": cur_bal,
            "minimum_balance_to_keep": min_bal,
            "max_installment_months": max_inst,
        }
    )

merged_by_id = {r["request_id"]: r for r in merged_records}

requests_df = pd.read_csv(os.path.join(DATA_DIR, "requests.csv")).set_index("request_id", drop=False)

# Pre-compute benchmark results against sample_requests.csv
# NOTE: sample_requests.csv is self-contained — IDs (request_01..request_25) are NOT
# in requests.csv (request_26..request_275). Each sample row includes all fields needed
# to run the engine directly, plus the ground-truth expected answers.
sample_eval_records = []
_s_matches = 0
_m_matches = 0
for s in raw_sample_requests:
    req_id = s.get("request_id", "")

    # Ground-truth labels are stored in the same columns as predictions in this file
    exp_status = s.get("affordability_status", "").strip()
    exp_method = s.get("recommended_payment_method", "").strip()

    # Use the sample row directly as the request dict
    req_dict = {
        "request_id": req_id,
        "user_id": s.get("user_id", ""),
        "request_date": s.get("request_date", ""),
        "requested_amount": s.get("requested_amount", "0"),
        "desired_completion_date": s.get("desired_completion_date", ""),
        "allows_partial_payment": s.get("allows_partial_payment", "False"),
        "request_type": s.get("request_type", "General"),
        "request_text": s.get("request_text", ""),
    }

    try:
        dec = Decision(engine_data, req_dict)
        r = dec.decide()
        got_status = r.get("affordability_status", "error")
        got_method = r.get("recommended_payment_method", "error")
        got_safe = float(r.get("amount_safe_to_pay", 0.0))
        explanation = r.get("decision_explanation", "")
    except (KeyError, ValueError, TypeError, IndexError) as err:
        got_status = "error"
        got_method = "error"
        got_safe = 0.0
        explanation = f"Evaluation error: {err}"

    s_match = exp_status == got_status
    m_match = exp_method == got_method
    if s_match:
        _s_matches += 1
    if m_match:
        _m_matches += 1

    user_id_val = s.get("user_id", "")
    user_cur = profiles_by_id.get(user_id_val, {}).get("home_currency", "USD")

    try:
        req_amt_val = float(s.get("requested_amount", 0.0))
    except (ValueError, TypeError):
        req_amt_val = 0.0

    sample_eval_records.append(
        {
            "request_id": req_id,
            "user_id": user_id_val,
            "request_date": s.get("request_date", ""),
            "requested_amount": req_amt_val,
            "requested_currency": user_cur,
            "category": s.get("request_type", "General"),
            "item_description": s.get("request_text", ""),
            "expected_status": exp_status,
            "predicted_status": got_status,
            "status_match": s_match,
            "expected_method": exp_method,
            "predicted_method": got_method,
            "method_match": m_match,
            "amount_safe_to_pay": got_safe,
            "decision_explanation": explanation,
        }
    )



class BuyOrWaitHandler(BaseHTTPRequestHandler):
    def send_json_response(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def serve_file(
        self,
        filepath: str,
        content_type: str = "text/html",
        as_attachment: bool = False,
        filename: str = "",
    ):
        if not os.path.exists(filepath):
            self.send_json_response({"detail": "File not found"}, 404)
            return

        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if as_attachment and filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Health check
        if path == "/api/health":
            self.send_json_response(
                {
                    "status": "online",
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "total_profiles": len(engine_data.profiles),
                    "total_events": len(engine_data.events),
                    "total_requests": len(raw_requests),
                    "total_outputs": len(raw_outputs),
                    "port": 5176,
                    "engine": "Deterministic Python Affordability Rules ($0.00 tokens)",
                }
            )
            return

        # 2. Static root and assets
        if path in ("", "/"):
            index_path = os.path.join(STATIC_DIR, "index.html")
            self.serve_file(index_path, "text/html; charset=utf-8")
            return

        if path.startswith("/static/"):
            rel_path = path[len("/static/") :]
            target_path = os.path.join(STATIC_DIR, rel_path.replace("/", os.sep))
            if os.path.isfile(target_path):
                mime, _ = mimetypes.guess_type(target_path)
                self.serve_file(target_path, mime or "application/octet-stream")
                return

        # 3. Overview API
        if path == "/api/overview":
            status_counts = defaultdict(int)
            method_counts = defaultdict(int)
            currency_counts = defaultdict(int)
            total_reqs = len(merged_records)

            total_requested_val = 0.0
            total_safe_val = 0.0

            for r in merged_records:
                status_counts[r["affordability_status"]] += 1
                method_counts[r["recommended_payment_method"]] += 1
                currency_counts[r["requested_currency"]] += 1

                try:
                    usd_requested = engine_data.rates.convert(
                        r["requested_amount"], r["requested_currency"], "USD"
                    )
                    usd_safe = engine_data.rates.convert(
                        r["amount_safe_to_pay"], r["home_currency"], "USD"
                    )
                    if usd_requested is not None:
                        total_requested_val += float(usd_requested)
                    if usd_safe is not None:
                        total_safe_val += float(usd_safe)
                except (KeyError, ValueError, TypeError, ZeroDivisionError) as err:
                    print(f"Currency conversion calculation error: {err}")

            self.send_json_response(
                {
                    "total_requests": total_reqs,
                    "status_breakdown": dict(status_counts),
                    "method_breakdown": dict(method_counts),
                    "currency_breakdown": dict(currency_counts),
                    "total_requested_usd": round(total_requested_val, 2),
                    "total_safe_usd": round(total_safe_val, 2),
                    "safe_ratio_pct": round(
                        (total_safe_val / max(total_requested_val, 1.0)) * 100, 1
                    ),
                    "sample_benchmark": {
                        "total_samples": len(sample_eval_records),
                        "status_matches": _s_matches,
                        "status_accuracy_pct": round(
                            (_s_matches / max(len(sample_eval_records), 1)) * 100, 1
                        ),
                        "method_matches": _m_matches,
                        "method_accuracy_pct": round(
                            (_m_matches / max(len(sample_eval_records), 1)) * 100, 1
                        ),
                    },
                }
            )
            return

        # 4. Filtered Requests list
        if path == "/api/requests":
            status_f = query.get("status", [""])[0].strip()
            method_f = query.get("method", [""])[0].strip()
            cur_f = query.get("currency", [""])[0].strip()
            q_search = query.get("search", [""])[0].lower().strip()
            limit_val = int(query.get("limit", [250])[0])

            res = []
            for r in merged_records:
                if status_f and r["affordability_status"] != status_f:
                    continue
                if method_f and r["recommended_payment_method"] != method_f:
                    continue
                if cur_f and r["requested_currency"] != cur_f:
                    continue
                if q_search:
                    search_blob = (
                        f"{r['request_id']} {r['user_id']} {r['category']} "
                        f"{r['item_description']} {r['decision_explanation']}"
                    ).lower()
                    if q_search not in search_blob:
                        continue
                res.append(r)
                if len(res) >= limit_val:
                    break

            self.send_json_response(
                {
                    "total_matched": len(res),
                    "total_records": len(merged_records),
                    "requests": res,
                }
            )
            return

        # 5. Single request detail with timeline
        if path.startswith("/api/requests/"):
            req_id = path[len("/api/requests/") :].strip()
            rec = merged_by_id.get(req_id)
            if not rec:
                self.send_json_response({"detail": "Request not found"}, 404)
                return

            user_id = rec["user_id"]
            req_date = _parse_date(rec["request_date"])
            forecast = None
            try:
                fc = UserForecast(engine_data, user_id, req_date)
                day_points = []
                base_d = req_date or dt.datetime.now(dt.timezone.utc).date()
                for d_idx, bal in enumerate(fc.day_balance):
                    curr_date = base_d + dt.timedelta(days=d_idx)
                    day_points.append(
                        {
                            "day": d_idx,
                            "date": curr_date.isoformat(),
                            "balance": round(bal, 2),
                            "min_reserve": round(fc.min_balance, 2),
                            "is_safe": bal >= fc.min_balance - 1e-6,
                        }
                    )

                events_breakdown = []
                for ev in fc.events_sorted:
                    d_val = ev["date"]
                    amt_val = ev["amount"]
                    events_breakdown.append(
                        {
                            "date": d_val.isoformat()
                            if hasattr(d_val, "isoformat")
                            else str(d_val),
                            "home_amount": round(abs(amt_val), 2),
                            "is_credit": amt_val >= 0,
                            "label": str(ev.get("event_id", "")),
                            "category": str(ev.get("category", "General")),
                        }
                    )

                forecast = {
                    "balance0": round(fc.balance0, 2),
                    "min_balance": round(fc.min_balance, 2),
                    "min_future": round(fc.min_future, 2),
                    "amount_safe_today": round(
                        fc.amount_safe_today(rec["requested_amount"]), 2
                    ),
                    "earliest_full_payment_offset": fc.earliest_full_payment_offset(
                        rec["requested_amount"]
                    ),
                    "timeline": day_points,
                    "events": events_breakdown[:40],
                }
            except (KeyError, ValueError, TypeError, IndexError) as err:
                print(f"Error computing forecast for {user_id}: {err}")

            matching_opts = payment_options_by_req.get(req_id, [])
            clean_opts = []
            for o in matching_opts:
                n_payments_raw = o.get("number_of_payments")
                n_payments = (
                    int(n_payments_raw)
                    if n_payments_raw is not None
                    and str(n_payments_raw) not in ("", "nan")
                    else 1
                )

                amt_raw = o.get("payment_amount")
                amt = (
                    float(amt_raw)
                    if amt_raw is not None and str(amt_raw) not in ("", "nan")
                    else 0.0
                )

                freq_val = o.get("payment_frequency_days")
                freq = (
                    int(freq_val)
                    if freq_val is not None and str(freq_val) not in ("", "nan")
                    else 30
                )

                interest_val = o.get("total_interest_amount")
                interest = (
                    float(interest_val)
                    if interest_val is not None and str(interest_val) not in ("", "nan")
                    else 0.0
                )

                fee_val = o.get("upfront_fee")
                fee = (
                    float(fee_val)
                    if fee_val is not None and str(fee_val) not in ("", "nan")
                    else 0.0
                )

                clean_opts.append(
                    {
                        "payment_option_id": o.get("payment_option_id"),
                        "payment_method": o.get("payment_method"),
                        "number_of_payments": n_payments,
                        "payment_amount": amt,
                        "first_payment_date": str(o.get("first_payment_date", "")),
                        "payment_frequency_days": freq,
                        "total_interest_amount": interest,
                        "upfront_fee": fee,
                    }
                )

            self.send_json_response(
                {"request": rec, "payment_options": clean_opts, "forecast": forecast}
            )
            return

        # 6. Samples benchmark endpoint
        if path == "/api/samples":
            n = len(sample_eval_records)
            self.send_json_response(
                {
                    "total_samples": n,
                    "status_accuracy_pct": round((_s_matches / max(n, 1)) * 100, 2),
                    "method_accuracy_pct": round((_m_matches / max(n, 1)) * 100, 2),
                    "samples": sample_eval_records,
                }
            )
            return

        # 7. Exchange rates endpoint - includes direct + computed cross-rates across all 5 currencies
        if path == "/api/rates":
            all_currencies = ["USD", "EUR", "INR", "IDR", "ZAR"]
            rates_list = []
            seen = set()
            for f in all_currencies:
                for t in all_currencies:
                    if f == t or (f, t) in seen:
                        continue
                    is_direct = (f, t) in engine_data.rates.rate
                    rate_val = engine_data.rates.convert(1.0, f, t)
                    if rate_val is not None:
                        rates_list.append(
                            {
                                "from_currency": f,
                                "to_currency": t,
                                "rate": round(rate_val, 6),
                                "is_direct": is_direct,
                            }
                        )
                        seen.add((f, t))
            # Sort: primary pairs with direct first or by currency
            rates_list.sort(key=lambda r: (r["from_currency"], r["to_currency"]))
            self.send_json_response(
                {
                    "currencies": all_currencies,
                    "rates": rates_list,
                }
            )
            return

        # 8. Currency conversion endpoint
        if path == "/api/convert":
            try:
                amount_str = query.get("amount", ["1000"])[0]
                from_cur = query.get("from_currency", ["USD"])[0]
                to_cur = query.get("to_currency", ["INR"])[0]
                amt = float(amount_str)
                res = engine_data.rates.convert(amt, from_cur, to_cur)
                if res is None:
                    self.send_json_response({"detail": "Conversion failed"}, 400)
                    return
                self.send_json_response(
                    {
                        "amount": amt,
                        "from_currency": from_cur,
                        "to_currency": to_cur,
                        "converted_amount": round(res, 2),
                        "rate": round(res / amt, 6),
                    }
                )
            except (ValueError, KeyError, TypeError, ZeroDivisionError) as err:
                self.send_json_response({"detail": str(err)}, 400)
            return

        # 9. All User Profiles endpoint (all 275 profiles)
        if path == "/api/profiles":
            profiles_list = []
            for p in raw_profiles:
                uid = str(p.get("user_id", "")).strip()
                profiles_list.append(
                    {
                        "user_id": uid,
                        "home_currency": p.get("home_currency", "USD"),
                        "current_available_balance": float(p.get("current_available_balance", 0.0) or 0.0),
                        "minimum_balance_to_keep": float(p.get("minimum_balance_to_keep", 0.0) or 0.0),
                        "max_installment_months": int(p.get("max_installment_months", 3) or 3),
                    }
                )
            profiles_list.sort(key=lambda x: int(x["user_id"].split("_")[1]) if "_" in x["user_id"] and x["user_id"].split("_")[1].isdigit() else 0)
            self.send_json_response(
                {
                    "total_profiles": len(profiles_list),
                    "profiles": profiles_list,
                }
            )
            return

        # 10. Download output.csv endpoint
        if path == "/api/download/output.csv":
            self.serve_file(
                OUT_PATH, "text/csv", as_attachment=True, filename="output.csv"
            )
            return

        # Fallback 404
        self.send_json_response({"detail": "Endpoint not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/simulate":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body_raw = self.rfile.read(content_len).decode("utf-8")
                body = json.loads(body_raw)

                raw_uid = str(body.get("user_id", "")).strip()
                user_id = raw_uid.lower()
                # Normalize formats like user_1 -> user_01
                if user_id.startswith("user_") and user_id[5:].isdigit():
                    num_val = int(user_id[5:])
                    if num_val < 100:
                        user_id = f"user_{num_val:02d}"
                    else:
                        user_id = f"user_{num_val}"

                if not user_id or user_id not in engine_data.profiles.index:
                    self.send_json_response(
                        {"detail": f"User '{raw_uid}' not found. Please select a valid profile from user_01 to user_275."}, 404
                    )
                    return

                user_prof = engine_data.profiles.loc[user_id]
                home_cur = str(user_prof.get("home_currency", "USD"))

                req_amt = float(body.get("requested_amount", 5000))
                requested_cur = str(body.get("requested_currency", home_cur)).strip() or home_cur
                req_date_str = str(body.get("request_date", "2025-01-15"))

                # Perform explicit FX conversion if requested currency differs from home currency
                is_cross_currency = (requested_cur != home_cur)
                if is_cross_currency:
                    converted = engine_data.rates.convert(req_amt, requested_cur, home_cur)
                    fx_rate = engine_data.rates.convert(1.0, requested_cur, home_cur)
                    if converted is not None and fx_rate is not None:
                        engine_amt = round(converted, 2)
                        conversion_info = {
                            "is_cross_currency": True,
                            "requested_amount": req_amt,
                            "requested_currency": requested_cur,
                            "home_currency": home_cur,
                            "converted_amount": engine_amt,
                            "exchange_rate": round(fx_rate, 4),
                            "display_text": f"{requested_cur} {req_amt:,.2f} ≈ {home_cur} {engine_amt:,.2f} (1 {requested_cur} = {fx_rate:,.2f} {home_cur})",
                        }
                    else:
                        engine_amt = req_amt
                        conversion_info = {
                            "is_cross_currency": False,
                            "requested_amount": req_amt,
                            "requested_currency": home_cur,
                            "home_currency": home_cur,
                            "converted_amount": req_amt,
                            "exchange_rate": 1.0,
                            "display_text": f"{home_cur} {req_amt:,.2f}",
                        }
                else:
                    engine_amt = req_amt
                    conversion_info = {
                        "is_cross_currency": False,
                        "requested_amount": req_amt,
                        "requested_currency": home_cur,
                        "home_currency": home_cur,
                        "converted_amount": req_amt,
                        "exchange_rate": 1.0,
                        "display_text": f"{home_cur} {req_amt:,.2f}",
                    }

                req_dict = {
                    "request_id": "sim_user_req",
                    "user_id": user_id,
                    "request_date": req_date_str,
                    "request_type": body.get("category", "purchase"),
                    "requested_amount": engine_amt,
                    "request_text": body.get("item_description", "Simulated Purchase"),
                    "desired_completion_date": str(
                        body.get("desired_completion_date", "2025-03-30")
                    ),
                    "allows_partial_payment": bool(
                        body.get("allows_partial_payment", True)
                    ),
                }

                # Synthesize standard 3-mo & 6-mo options for simulation in home currency
                n3 = 3
                n6 = 6
                opts_list = [
                    {
                        "payment_option_id": "sim_opt_3mo",
                        "request_id": "sim_user_req",
                        "payment_method": "installments",
                        "number_of_payments": n3,
                        "payment_amount": round(engine_amt / n3, 2),
                        "first_payment_date": req_date_str,
                        "payment_frequency_days": 30,
                        "total_interest_amount": 0.0,
                        "upfront_fee": 0.0,
                    },
                    {
                        "payment_option_id": "sim_opt_6mo",
                        "request_id": "sim_user_req",
                        "payment_method": "installments",
                        "number_of_payments": n6,
                        "payment_amount": round((engine_amt * 1.05) / n6, 2),
                        "first_payment_date": req_date_str,
                        "payment_frequency_days": 30,
                        "total_interest_amount": round(engine_amt * 0.05, 2),
                        "upfront_fee": 0.0,
                    },
                ]
                sim_options_df = pd.DataFrame(opts_list)

                old_opts = engine_data.payment_options
                engine_data.payment_options = pd.concat(
                    [old_opts, sim_options_df], ignore_index=True
                )

                try:
                    dec = Decision(engine_data, pd.Series(req_dict))
                    result = dec.decide()

                    fc = dec.fc
                    day_points = []
                    base_d = (
                        dec.request_date
                        or dt.datetime.now(dt.timezone.utc).date()
                    )
                    min_projected_balance = round(min(fc.day_balance), 2)
                    first_breach_day = None

                    for d_idx, bal in enumerate(fc.day_balance):
                        curr_date = base_d + dt.timedelta(days=d_idx)
                        is_safe_pt = bal >= fc.min_balance - 1e-6
                        if not is_safe_pt and first_breach_day is None:
                            first_breach_day = {
                                "day": d_idx,
                                "date": curr_date.isoformat(),
                                "balance": round(bal, 2),
                                "breach_amount": round(fc.min_balance - bal, 2),
                            }

                        day_points.append(
                            {
                                "day": d_idx,
                                "date": curr_date.isoformat(),
                                "balance": round(bal, 2),
                                "min_reserve": round(fc.min_balance, 2),
                                "is_safe": is_safe_pt,
                            }
                        )

                    timeline_data = {
                        "balance0": round(fc.balance0, 2),
                        "min_balance": round(fc.min_balance, 2),
                        "amount_safe_today": round(fc.amount_safe_today(engine_amt), 2),
                        "min_projected_balance": min_projected_balance,
                        "first_breach_day": first_breach_day,
                        "timeline": day_points,
                    }

                    self.send_json_response(
                        {
                            "success": True,
                            "decision": result,
                            "timeline": timeline_data,
                            "conversion": conversion_info,
                            "user_profile": {
                                "user_id": user_id,
                                "home_currency": fc.home_currency,
                                "current_available_balance": fc.balance0,
                                "minimum_balance_to_keep": fc.min_balance,
                            },
                        }
                    )
                finally:
                    engine_data.payment_options = old_opts

            except (KeyError, ValueError, TypeError, json.JSONDecodeError) as err:
                self.send_json_response({"detail": f"Simulation processing error: {err}"}, 500)
            return

        self.send_json_response({"detail": "Not Found"}, 404)


def run_server(port: int = 5176):
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, BuyOrWaitHandler)
    print(f"Buy or Wait? server listening at http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server(5176)
