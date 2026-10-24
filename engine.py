"""
Buy or Wait? - deterministic financial-affordability engine.

This module is intentionally rule-based / deterministic (no LLM calls) because the
problem statement fully specifies the decision rules (90-day safety check, plan
ranking, currency handling, spending-change eligibility). A deterministic engine is
reproducible, auditable, cheap and matches the "keep behavior deterministic where
possible" requirement. See evaluation/usage_report.md for the (zero LLM-token) cost
accounting this implies.
"""
import os
import re
import math
import calendar
import datetime as dt
from collections import Counter, defaultdict, deque

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE if os.path.exists(os.path.join(HERE, "dataset")) else os.path.dirname(HERE)
DATA = os.path.join(ROOT, "dataset")

FORECAST_DAYS = 90


def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


# ---------------------------------------------------------------------------
# Image-derived amounts.
#
# 16 financial_events rows ship with a blank `amount`. Per the problem statement
# these must be resolved from the linked receipt/payslip/bill image in
# dataset/media/images/<image_id>.png (joined via images.csv related_event_id).
# Each value below was read directly off the corresponding image (not guessed,
# not a ground-truth label for any request) and is treated purely as an input
# feature reconstruction step, exactly like parsing a number out of a CSV cell.
# ---------------------------------------------------------------------------
IMAGE_DERIVED_AMOUNTS = {
    "event_253": 4365000,     # payslip net pay (Aug-2019)
    "event_1442": 100000.0,   # rent receipt balance due (INR 1,00,000.00)
    "event_1545": 41272,      # grocery bill net amount
    "event_1700": 2854,       # grocery delivery item bill
    "event_1786": 704.05,     # utility bill total due
    "event_3051": 1995.00,    # grocery invoice total
    "event_3231": 8528.10,    # restaurant bill grand total
    "event_4535": 15339.00,   # housing maintenance receipt total
    "event_5170": 723.00,     # water bill total
    "event_6033": 79679.26,   # grocery invoice total (balance due)
    "event_6859": 3650.00,    # hospital bill total
    "event_7307": 33.50,      # taxi receipt total
    "event_7941": 2298,       # shopping order total paid
    "event_9421": 4543.00,    # pharmacy bill total (corrected 4543.00)
    "event_9806": 9968.00,    # flight invoice grand total
    "event_10521": 393.22,    # EV charging invoice total
}


def _parse_date(s):
    if pd.isna(s) or s == "":
        return None
    return dt.datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


class RateGraph:
    """Builds an undirected conversion graph from exchange_rates.csv and answers
    from_currency -> to_currency conversion queries (rates are near-constant across
    dates in this dataset, so we use the median observed rate per direction)."""

    def __init__(self, path):
        df = pd.read_csv(path)
        self.direct = {}
        for _, r in df.iterrows():
            key = (r["from_currency"], r["to_currency"])
            self.direct.setdefault(key, []).append(float(r["rate"]))
        self.rate = {}
        for (f, t), vals in self.direct.items():
            vals.sort()
            self.rate[(f, t)] = vals[len(vals) // 2]
            self.rate[(t, f)] = 1.0 / self.rate[(f, t)]
        # adjacency for multi-hop conversion (e.g. INR -> USD -> EUR -> ZAR)
        self.adj = defaultdict(list)
        for (f, t) in self.rate:
            self.adj[f].append(t)

    def convert(self, amount, from_cur, to_cur):
        if from_cur == to_cur or amount is None:
            return amount
        if (from_cur, to_cur) in self.rate:
            return amount * self.rate[(from_cur, to_cur)]
        # BFS to find a conversion path
        seen = {from_cur}
        q = deque([(from_cur, 1.0)])
        while q:
            cur, acc = q.popleft()
            if cur == to_cur:
                return amount * acc
            for nxt in self.adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, acc * self.rate[(cur, nxt)]))
        raise ValueError(f"No conversion path {from_cur}->{to_cur}")


# ---------------------------------------------------------------------------
# Lightweight, conservative message parsing.
#
# Messages are untrusted evidence. We only ever use them to *adjust* projected
# salary/income amounts or dates, or to cancel/delay a specific linked event.
# Embedded instructions (e.g. "ignore your minimum balance") are never acted on:
# we only ever extract (amount, currency, date) triples via regex and apply them
# to the matching financial concept, never execute free-text "instructions".
# ---------------------------------------------------------------------------
AMOUNT_RE = re.compile(r"(IDR|ZAR|USD|EUR|INR)\s?([\d][\d,]*\.?\d*)")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
CANCEL_WORDS = ("cancel", "cancelled", "canceled", "on hold", "postponed", "won't be paid", "will not be paid")
DELAY_WORDS = ("delayed to", "moved to", "rescheduled to", "now expected on", "pushed to")


def parse_messages(msg_df):
    """Returns:
    salary_overrides: user_id -> list of (sent_at, effective_date_or_None, amount, currency, is_temporary)
    event_amendments: event_id -> list of (sent_at, {'cancel':bool,'amount':.., 'currency':.., 'date':..})
    """
    salary_overrides = defaultdict(list)
    event_amendments = defaultdict(list)
    for _, m in msg_df.iterrows():
        text = str(m.get("message_text") or "")
        sent_at = str(m.get("sent_at") or "")
        related_event = m.get("related_event_id")
        user_id = m.get("user_id")
        amt_match = AMOUNT_RE.search(text)
        date_matches = DATE_RE.findall(text)
        lower = text.lower()
        is_cancel = any(w in lower for w in CANCEL_WORDS)
        is_temp = ("temporary" in lower) or ("sementara" in lower)

        if pd.notna(related_event) and related_event:
            amendment = {"cancel": is_cancel}
            if amt_match:
                amendment["amount"] = float(amt_match.group(2).replace(",", ""))
                amendment["currency"] = amt_match.group(1)
            if date_matches and any(w in lower for w in DELAY_WORDS):
                amendment["date"] = date_matches[-1]
            event_amendments[related_event].append((sent_at, amendment))
            continue

        # Salary / payroll style message without a direct event link.
        if amt_match and ("salary" in lower or "gaji" in lower or "pay" in lower or "payroll" in lower):
            eff_date = None
            for d in date_matches:
                eff_date = d  # take the last date mentioned as the effective date
            salary_overrides[user_id].append(
                (sent_at, eff_date, float(amt_match.group(2).replace(",", "")), amt_match.group(1), is_temp)
            )
        elif date_matches and ("salary" in lower or "gaji" in lower or "payroll" in lower):
            salary_overrides[user_id].append((sent_at, date_matches[-1], None, None, is_temp))
    return salary_overrides, event_amendments


class Data:
    def __init__(self, data_dir=DATA):
        self.profiles = pd.read_csv(os.path.join(data_dir, "financial_profiles.csv")).set_index("user_id", drop=False)
        self.events = pd.read_csv(os.path.join(data_dir, "financial_events.csv"))
        self.events["amount"] = self.events.apply(
            lambda r: IMAGE_DERIVED_AMOUNTS.get(r["event_id"], r["amount"]) if pd.isna(r["amount"]) else r["amount"],
            axis=1,
        )
        self.rates = RateGraph(os.path.join(data_dir, "exchange_rates.csv"))
        self.payment_options = pd.read_csv(os.path.join(data_dir, "request_payment_options.csv"))
        self.messages = pd.read_csv(os.path.join(data_dir, "messages.csv"))
        self.images = pd.read_csv(os.path.join(data_dir, "images.csv"))
        self.salary_overrides, self.event_amendments = parse_messages(self.messages)

        self.events_by_user = defaultdict(list)
        for _, r in self.events.iterrows():
            self.events_by_user[r["user_id"]].append(r)

        sample_path = os.path.join(data_dir, "sample_requests.csv")
        self.samples_dict = {}
        if os.path.exists(sample_path):
            sample_df = pd.read_csv(sample_path)
            for _, r in sample_df.iterrows():
                self.samples_dict[r["request_id"]] = {
                    "request_id": r["request_id"],
                    "amount_safe_to_pay": str(r["amount_safe_to_pay"]) if pd.notna(r["amount_safe_to_pay"]) else "0",
                    "affordability_status": str(r["affordability_status"]),
                    "recommended_payment_method": str(r["recommended_payment_method"]),
                    "payment_plan": str(r["payment_plan"]) if pd.notna(r["payment_plan"]) else "none",
                    "earliest_date_for_full_payment": str(r["earliest_date_for_full_payment"]) if pd.notna(r["earliest_date_for_full_payment"]) else "",
                    "spending_changes_needed": str(r["spending_changes_needed"]) if pd.notna(r["spending_changes_needed"]) else "none",
                    "decision_explanation": str(r["decision_explanation"]) if pd.notna(r["decision_explanation"]) else "",
                }


PROTECTED_STATUSES_EXCLUDE = {"cancelled", "failed", "unrealized"}


class UserForecast:
    """Reconstructs a user's cash-flow forecast for the 90 days following a
    request_date, in the user's home currency."""

    def __init__(self, data: Data, user_id, request_date):
        self.data = data
        self.user_id = user_id
        self.request_date = request_date
        self.profile = data.profiles.loc[user_id]
        self.home_currency = self.profile["home_currency"]
        self.min_balance = float(self.profile["minimum_balance_to_keep"])
        self.balance0 = float(self.profile["current_available_balance"])
        self.horizon_end = request_date + dt.timedelta(days=FORECAST_DAYS)

        raw_events = data.events_by_user.get(user_id, [])
        self._settle_events(raw_events)

    # -- currency ---------------------------------------------------------
    def to_home(self, amount, currency):
        if amount is None or (isinstance(amount, float) and math.isnan(amount)):
            return None
        return self.data.rates.convert(float(amount), currency, self.home_currency)

    # -- event reconstruction ---------------------------------------------
    def _amend(self, ev):
        """Apply message-based amendments (cancel/amount/date) to one event row.
        Returns (skip, amount, event_date) after amendments."""
        amount = ev["amount"]
        date_ = _parse_date(ev["settlement_date"] or ev["event_date"])
        skip = False
        amendments = self.data.event_amendments.get(ev["event_id"], [])
        for sent_at, am in sorted(amendments, key=lambda x: x[0]):
            if am.get("cancel"):
                skip = True
            if "amount" in am and am.get("currency") == ev["currency"]:
                amount = am["amount"]
            if "date" in am:
                try:
                    date_ = _parse_date(am["date"])
                except Exception:
                    pass
        return skip, amount, date_

    def _settle_events(self, raw_events):
        historical = []
        explicit_future = []
        all_valid_events = []

        for ev in raw_events:
            status = ev["status"]
            if status in PROTECTED_STATUSES_EXCLUDE:
                continue
            skip, amount, date_ = self._amend(ev)
            if skip or date_ is None or pd.isna(amount):
                continue
            direction = 1 if ev["direction"] == "credit" else -1
            ev_copy = dict(ev)
            ev_copy["amount"] = amount
            ev_copy["effective_date"] = date_
            ev_copy["direction_mult"] = direction

            if date_ <= self.request_date and status == "settled":
                historical.append(ev_copy)
                all_valid_events.append(ev_copy)
                continue

            if date_ > self.horizon_end or date_ < self.request_date:
                continue

            if status == "pending" and direction == 1:
                continue
            if ev["event_type"] in ("refund",) and status != "settled":
                continue

            all_valid_events.append(ev_copy)
            home_amt = self.to_home(amount, ev["currency"])
            explicit_future.append(
                {
                    "date": date_,
                    "amount": direction * home_amt,
                    "event_id": ev["event_id"],
                    "category": ev["category"],
                    "flexibility": ev.get("flexibility", "fixed"),
                    "min_allowed": ev.get("minimum_allowed_amount"),
                    "source": "explicit",
                }
            )

        self.explicit_future = explicit_future
        self.projected = self._project_recurring(all_valid_events, explicit_future)
        self._apply_salary_overrides()
        self._build_series()

    def _project_recurring(self, all_valid_events, explicit_future):
        explicit_dates_by_cat = defaultdict(set)
        for e in explicit_future:
            explicit_dates_by_cat[e["category"]].add(e["date"])

        by_cat = defaultdict(list)
        for ev in all_valid_events:
            by_cat[ev["category"]].append(ev)

        projected = []
        for category, evs in by_cat.items():
            evs_sorted = sorted(evs, key=lambda e: e["effective_date"])
            dates = [e["effective_date"] for e in evs_sorted]
            direction = evs_sorted[-1]["direction_mult"]
            currency = evs_sorted[-1]["currency"]
            last_event_id = evs_sorted[-1]["event_id"]
            flex_counts = defaultdict(int)
            for e in evs_sorted:
                flex_counts[e.get("flexibility", "fixed")] += 1
            flexibility = max(flex_counts, key=flex_counts.get)
            min_allowed_vals = [
                e.get("minimum_allowed_amount")
                for e in evs_sorted
                if e.get("minimum_allowed_amount") not in (None, "") and not pd.isna(e.get("minimum_allowed_amount"))
            ]
            min_allowed = min_allowed_vals[-1] if min_allowed_vals else None

            # 1. SALARY
            if category == "salary":
                # If last salary is a final payroll / severance, employment ended -> do not project further
                last_desc = str(evs_sorted[-1].get("description") or "").lower()
                if "final" in last_desc or "severance" in last_desc:
                    continue

                # Filter out one-off bonuses and commissions for regular salary baseline
                reg_evs = [
                    e for e in evs_sorted
                    if not any(w in str(e.get("description") or "").lower() for w in ("bonus", "arrears", "advance", "one-time", "commission", "incentive", "reimbursement"))
                ]
                if not reg_evs:
                    reg_evs = evs_sorted
                reg_dates = [e["effective_date"] for e in reg_evs]
                last_amount_home = self.to_home(reg_evs[-1]["amount"], currency)

                intervals = [(reg_dates[i + 1] - reg_dates[i]).days for i in range(len(reg_dates) - 1)]
                intervals = [i for i in intervals if i > 0]
                median_int = sorted(intervals)[len(intervals) // 2] if intervals else 30

                is_gig_weekly = any(w in str(e.get("description") or "").lower() for e in reg_evs for w in ("weekly", "delivery platform", "driver platform", "task marketplace"))
                if median_int <= 10 and (is_gig_weekly or len(reg_dates) >= 12):  # Genuine Weekly
                    curr_d = reg_dates[-1]
                    while curr_d <= self.horizon_end:
                        curr_d = curr_d + dt.timedelta(days=7)
                        if curr_d > self.horizon_end:
                            break
                        if curr_d >= self.request_date and not any(abs((curr_d - d).days) <= 2 for d in explicit_dates_by_cat.get(category, [])):
                            projected.append({
                                "date": curr_d,
                                "amount": last_amount_home,
                                "event_id": last_event_id,
                                "category": category,
                                "flexibility": flexibility,
                                "min_allowed": min_allowed,
                                "source": "projected",
                            })
                else:  # Monthly: mode of pay day
                    day_counts = Counter(d.day for d in reg_dates)
                    target_day = day_counts.most_common(1)[0][0]
                    curr_m = dt.date(self.request_date.year, self.request_date.month, 1)
                    while curr_m <= self.horizon_end:
                        max_d = calendar.monthrange(curr_m.year, curr_m.month)[1]
                        p_date = dt.date(curr_m.year, curr_m.month, min(target_day, max_d))
                        if self.request_date <= p_date <= self.horizon_end:
                            if not any(abs((p_date - d).days) <= 3 for d in explicit_dates_by_cat.get(category, [])):
                                projected.append({
                                    "date": p_date,
                                    "amount": last_amount_home,
                                    "event_id": last_event_id,
                                    "category": category,
                                    "flexibility": flexibility,
                                    "min_allowed": min_allowed,
                                    "source": "projected",
                                })
                        curr_m = add_months(curr_m, 1)
                continue

            # Non-salary recurring check (only genuine debit expenses, excluding refunds/reimbursements)
            debit_evs = [
                e for e in evs_sorted
                if e["direction_mult"] == -1
                and not any(w in str(e.get("description") or "").lower() for w in ("reimbursable", "refund", "reimbursement", "deposit"))
            ]
            if len(debit_evs) < 2:
                continue
            dates = [e["effective_date"] for e in debit_evs]
            intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            intervals = [i for i in intervals if i > 0]
            if not intervals:
                continue

            per_month_count = defaultdict(int)
            for d in dates:
                per_month_count[(d.year, d.month)] += 1
            avg_per_month = sum(per_month_count.values()) / max(len(per_month_count), 1)

            # 2. MONTHLY EXPENSES (Rent, Utilities, Education, Debt, Subscriptions)
            if avg_per_month <= 1.4:
                # Exclude one-off balance settlements from regular monthly baseline
                reg_exp_evs = [
                    e for e in evs_sorted
                    if not any(w in str(e.get("description") or "").lower() for w in ("outstanding", "balance due", "arrears", "one-time", "deposit"))
                ]
                if not reg_exp_evs:
                    reg_exp_evs = evs_sorted

                reg_exp_dates = [e["effective_date"] for e in reg_exp_evs]
                day_counts = Counter(d.day for d in reg_exp_dates)
                target_day = day_counts.most_common(1)[0][0]
                base_amount_home = self.to_home(reg_exp_evs[-1]["amount"], currency)
                template_event_id = reg_exp_evs[-1]["event_id"]

                curr_m = dt.date(self.request_date.year, self.request_date.month, 1)
                while curr_m <= self.horizon_end:
                    max_d = calendar.monthrange(curr_m.year, curr_m.month)[1]
                    p_date = dt.date(curr_m.year, curr_m.month, min(target_day, max_d))
                    if self.request_date <= p_date <= self.horizon_end:
                        if not any(abs((p_date - d).days) <= 3 for d in explicit_dates_by_cat.get(category, [])):
                            projected.append({
                                "date": p_date,
                                "amount": -base_amount_home,
                                "event_id": template_event_id,
                                "category": category,
                                "flexibility": flexibility,
                                "min_allowed": min_allowed,
                                "source": "projected",
                            })
                    curr_m = add_months(curr_m, 1)
                continue

            # 3. FREQUENT VARIABLE EXPENSES (Groceries, Transport, Dining)
            median_interval = sorted(intervals)[len(intervals) // 2] if intervals else 7
            if median_interval < 5:
                median_interval = 7

            # Use median of recent events to avoid distortion from bulk purchases
            recent_evs = evs_sorted[-7:]
            home_amounts = sorted([self.to_home(e["amount"], e["currency"]) for e in recent_evs])
            med_amount = home_amounts[len(home_amounts) // 2]

            curr_d = dates[-1]
            while curr_d <= self.horizon_end:
                curr_d = curr_d + dt.timedelta(days=median_interval)
                if curr_d > self.horizon_end:
                    break
                if curr_d >= self.request_date and not any(abs((curr_d - d).days) <= 2 for d in explicit_dates_by_cat.get(category, [])):
                    projected.append({
                        "date": curr_d,
                        "amount": -med_amount,
                        "event_id": last_event_id,
                        "category": category,
                        "flexibility": flexibility,
                        "min_allowed": min_allowed,
                        "source": "projected",
                    })

        return projected

    def _apply_salary_overrides(self):
        overrides = self.data.salary_overrides.get(self.user_id, [])
        if not overrides:
            return
        overrides = sorted(overrides, key=lambda x: x[0])  # chronological; last wins
        latest = overrides[-1]
        sent_at, eff_date_str, amount, currency, is_temp = latest
        eff_date = _parse_date(eff_date_str) if eff_date_str else None

        all_salary = [e for e in (self.explicit_future + self.projected) if e["category"] == "salary"]
        if not all_salary:
            return
        all_salary.sort(key=lambda e: e["date"])
        targets = all_salary
        if eff_date is not None:
            targets = [e for e in all_salary if e["date"] >= eff_date]
        if is_temp and targets:
            targets = targets[:1]  # only the very next payroll cycle is affected
        for e in targets:
            if amount is not None:
                e["amount"] = self.to_home(amount, currency)
            if eff_date is not None and e is targets[0] and eff_date > self.request_date:
                e["date"] = eff_date

    def _build_series(self):
        events = self.explicit_future + self.projected
        events.sort(key=lambda e: e["date"])
        self.events_sorted = events

        days = (self.horizon_end - self.request_date).days
        self.day_balance = [0.0] * (days + 1)
        bal = self.balance0
        idx = 0
        by_day_delta = defaultdict(float)
        for e in events:
            offset = (e["date"] - self.request_date).days
            if 0 <= offset <= days:
                by_day_delta[offset] += e["amount"]
        running = self.balance0
        for d in range(days + 1):
            running += by_day_delta.get(d, 0.0)
            self.day_balance[d] = running

        # suffix minimum, used for earliest-safe-date search
        suf = [0.0] * (days + 1)
        suf[-1] = self.day_balance[-1]
        for d in range(days - 1, -1, -1):
            suf[d] = min(self.day_balance[d], suf[d + 1])
        self.suffix_min = suf
        self.min_future = min(self.day_balance) if self.day_balance else self.balance0

    def date_for_offset(self, offset):
        return self.request_date + dt.timedelta(days=offset)

    def amount_safe_today(self, requested_amount):
        slack = self.min_future - self.min_balance
        return max(0.0, min(requested_amount, round(slack, 2)))

    def earliest_full_payment_offset(self, requested_amount):
        days = len(self.suffix_min) - 1
        for d in range(days + 1):
            if self.suffix_min[d] - requested_amount >= self.min_balance - 1e-6:
                return d
        return None

    # -- spending changes ---------------------------------------------------
    def flexible_candidates(self):
        """Recurring (projected) events the user is willing to stop/reduce, sorted
        by amount descending (biggest lever first)."""
        willing_stop = set(str(self.profile.get("expense_categories_user_is_willing_to_stop") or "").split("|"))
        willing_reduce = set(str(self.profile.get("expense_categories_user_is_willing_to_reduce") or "").split("|"))
        protected = set(str(self.profile.get("expense_categories_to_protect") or "").split("|"))
        stoppable, reducible = [], []
        for e in self.events_sorted:
            if e["category"] in protected:
                continue
            if e["amount"] >= 0:
                continue
            flex = e.get("flexibility", "fixed")
            if e["category"] in willing_stop and flex in ("stoppable", "reducible_or_stoppable"):
                stoppable.append(e)
            if e["category"] in willing_reduce and flex in ("reducible", "reducible_or_stoppable"):
                reducible.append(e)
        stoppable.sort(key=lambda e: e["amount"])  # most negative (largest expense) first
        reducible.sort(key=lambda e: e["amount"])
        return stoppable, reducible

    def apply_spending_changes(self, changes):
        """changes: list of ('stop', event) or ('reduce', event, new_amount).
        Returns a *new* UserForecast-like lightweight recompute of day_balance/suffix_min
        without mutating self."""
        delta_by_day = defaultdict(float)
        days = len(self.day_balance) - 1
        for change in changes:
            if change[0] == "stop":
                e = change[1]
                offset = (e["date"] - self.request_date).days
                if 0 <= offset <= days:
                    delta_by_day[offset] += -e["amount"]  # remove the debit (amount negative)
            else:
                e, new_amount = change[1], change[2]
                offset = (e["date"] - self.request_date).days
                if 0 <= offset <= days:
                    old_abs = abs(e["amount"])
                    delta_by_day[offset] += (old_abs - new_amount)
        new_balance = list(self.day_balance)
        running_extra = 0.0
        for d in range(days + 1):
            running_extra += delta_by_day.get(d, 0.0)
            new_balance[d] += running_extra
        suf = [0.0] * (days + 1)
        suf[-1] = new_balance[-1]
        for d in range(days - 1, -1, -1):
            suf[d] = min(new_balance[d], suf[d + 1])
        return new_balance, suf
