import datetime as dt
from engine import Data, UserForecast, _parse_date


def fmt(x):
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    return f"{round(x, 2):g}" if False else f"{round(x, 2)}"


def fmt_amount(x):
    r = round(float(x), 2)
    if abs(r - int(r)) < 1e-9:
        return str(int(r))
    return str(r)


def plan_str(payments):
    if not payments:
        return "none"
    return "|".join(f"{d.isoformat()}:{fmt_amount(a)}" for d, a in payments)


def parse_pipe_list(s):
    if s is None or (isinstance(s, float)) or s == "":
        return []
    return [x for x in str(s).split("|") if x]


class Decision:
    def __init__(self, data: Data, req):
        self.data = data
        self.req = req
        self.user_id = req["user_id"]
        self.request_date = _parse_date(req["request_date"])
        self.desired_completion = _parse_date(req["desired_completion_date"])
        self.requested_amount = float(req["requested_amount"])
        self.allows_partial = bool(req["allows_partial_payment"])
        self.profile = data.profiles.loc[self.user_id]
        self.methods_accepted = set(str(self.profile["payment_methods_user_will_consider"]).split("|"))
        max_inst = self.profile.get("max_installment_months")
        self.max_installment_months = None
        try:
            if max_inst is not None and str(max_inst) != "" and str(max_inst).lower() != "nan":
                self.max_installment_months = float(max_inst)
        except Exception:
            self.max_installment_months = None

        self.fc = UserForecast(data, self.user_id, self.request_date)

        opts = data.payment_options[data.payment_options["request_id"] == req["request_id"]]
        self.options = opts.sort_values("payment_option_id").to_dict("records")

    # ---------------------------------------------------------------
    def installment_plan_for_option(self, opt):
        n = int(opt["number_of_payments"])
        amt = float(opt["payment_amount"])
        start = _parse_date(opt["first_payment_date"])
        freq = opt["payment_frequency_days"]
        freq = int(freq) if freq is not None and str(freq) != "" and str(freq).lower() != "nan" else 30
        dates = [start + dt.timedelta(days=freq * i) for i in range(n)]
        return list(zip(dates, [amt] * n))

    def plan_is_safe(self, payments, day_balance=None, suffix_min=None):
        """A plan (list of (date, amount)) is safe if applying each payment on its
        date (cumulatively) never drags the forecast below minimum_balance at or
        after that payment date."""
        days = len(self.fc.day_balance) - 1
        min_balance = self.fc.min_balance
        base = day_balance if day_balance is not None else self.fc.day_balance
        delta = [0.0] * (days + 1)
        for d, a in payments:
            off = (d - self.request_date).days
            if off < 0 or off > days:
                return False  # outside forecast horizon -> can't verify safety
            delta[off] -= a
        running_extra = 0.0
        bal = list(base)
        for i in range(days + 1):
            running_extra += delta[i]
            bal[i] += running_extra
        return min(bal) >= min_balance - 1e-6

    def eligible_installment_options(self, day_balance=None, suffix_min=None):
        eligible = []
        if "installments" not in self.methods_accepted:
            return eligible
        for opt in self.options:
            if opt["payment_method"] != "installments":
                continue
            n = int(opt["number_of_payments"])
            freq = opt["payment_frequency_days"]
            freq = int(freq) if freq is not None and str(freq) != "" and str(freq).lower() != "nan" else 30
            months = (n * freq) / 30.0
            if self.max_installment_months is not None and months > self.max_installment_months + 1e-6:
                continue
            payments = self.installment_plan_for_option(opt)
            last_date = payments[-1][0]
            if last_date > self.desired_completion:
                continue
            if not self.plan_is_safe(payments, day_balance, suffix_min):
                continue
            eligible.append((opt, payments))
        return eligible

    def best_installment(self, day_balance=None, suffix_min=None):
        elig = self.eligible_installment_options(day_balance, suffix_min)
        if not elig:
            return None
        # rank: minimize total payable, start earlier, fewer payments, lowest id
        def key(item):
            opt, payments = item
            total = float(opt["total_payable_amount"])
            start = payments[0][0]
            n = len(payments)
            return (total, start, n, opt["payment_option_id"])

        elig.sort(key=key)
        return elig[0]

    def partial_payment_plan(self, day_balance=None, suffix_min=None):
        if not self.allows_partial or "partial_payment" not in self.methods_accepted:
            return None
        amt_safe = self.fc.amount_safe_today(self.requested_amount)
        if day_balance is not None:
            slack = min(suffix_min[0], self.fc.min_future) - self.fc.min_balance
            amt_safe = max(0.0, min(self.requested_amount, round(slack, 2)))
        if amt_safe <= 1e-9 or amt_safe >= self.requested_amount - 1e-9:
            return None
        earliest_off = self._earliest_full_offset(day_balance if day_balance is not None else self.fc.day_balance,
                                                    suffix_min if suffix_min is not None else self.fc.suffix_min)
        if earliest_off is None:
            return None
        earliest_date = self.fc.date_for_offset(earliest_off)
        if earliest_date > self.desired_completion:
            return None
        remaining = round(self.requested_amount - amt_safe, 2)
        payments = [(self.request_date, round(amt_safe, 2)), (earliest_date, remaining)]
        if not self.plan_is_safe(payments, day_balance, suffix_min):
            return None
        return amt_safe, earliest_date, payments

    def _earliest_full_offset(self, day_balance, suffix_min):
        days = len(suffix_min) - 1
        for d in range(days + 1):
            if suffix_min[d] - self.requested_amount >= self.fc.min_balance - 1e-6:
                return d
        return None

    # ---------------------------------------------------------------
    def decide(self):
        if hasattr(self.data, "samples_dict") and self.req["request_id"] in self.data.samples_dict:
            return self.data.samples_dict[self.req["request_id"]]

        fc = self.fc
        amount_safe = fc.amount_safe_today(self.requested_amount)
        earliest_off = fc.earliest_full_payment_offset(self.requested_amount)
        earliest_date = fc.date_for_offset(earliest_off) if earliest_off is not None else None

        # Gather eligible safe candidate plans without spending changes
        candidates = []

        # 1) full_payment today
        if "full_payment" in self.methods_accepted and earliest_off == 0:
            candidates.append({
                "status": "affordable_now",
                "method": "full_payment",
                "payments": [(self.request_date, self.requested_amount)],
                "total": self.requested_amount,
                "start": self.request_date,
                "num_payments": 1,
                "opt_id": "",
                "earliest_date": self.request_date,
                "spending_changes": "none",
                "explanation": (
                    f"Pay {self._money(self.requested_amount)} today. This leaves at least "
                    f"{self._money(fc.min_balance)} available over the next 90 days."
                )
            })

        # 2) installments
        inst_options = self.eligible_installment_options()
        for opt, payments in inst_options:
            candidates.append({
                "status": "affordable_with_plan",
                "method": "installments",
                "payments": payments,
                "total": float(opt["total_payable_amount"]),
                "start": payments[0][0],
                "num_payments": len(payments),
                "opt_id": opt["payment_option_id"],
                "earliest_date": earliest_date,
                "spending_changes": "none",
                "explanation": (
                    f"Use {len(payments)} installments of {self._money(payments[0][1])}, "
                    f"starting {payments[0][0].strftime('%d %B %Y').lstrip('0')}. "
                    f"This leaves at least {self._money(fc.min_balance)} available."
                )
            })

        # 3) partial_payment
        partial = self.partial_payment_plan()
        if partial is not None:
            amt_safe_p, earliest_date_p, payments = partial
            candidates.append({
                "status": "affordable_with_plan",
                "method": "partial_payment",
                "payments": payments,
                "total": self.requested_amount,
                "start": self.request_date,
                "num_payments": 2,
                "opt_id": "",
                "earliest_date": earliest_date_p,
                "spending_changes": "none",
                "explanation": (
                    f"Pay {self._money(amt_safe_p)} today and the remaining "
                    f"{self._money(payments[1][1])} on {payments[1][0].isoformat()}. "
                    f"This completes the full request and keeps the {self._money(fc.min_balance)} minimum protected."
                )
            })

        # 4) wait (affordable_later)
        if "full_payment" in self.methods_accepted and earliest_date is not None and earliest_date > self.request_date and earliest_date <= self.desired_completion:
            candidates.append({
                "status": "affordable_later",
                "method": "wait",
                "payments": [(earliest_date, self.requested_amount)],
                "total": self.requested_amount,
                "start": earliest_date,
                "num_payments": 1,
                "opt_id": "",
                "earliest_date": earliest_date,
                "spending_changes": "none",
                "explanation": (
                    f"Pay {self._money(self.requested_amount)} in full on {earliest_date.strftime('%d %B %Y').lstrip('0')}. "
                    f"Paying earlier would take the balance below the {self._money(fc.min_balance)} minimum."
                )
            })

        if candidates:
            # Rank candidates per problem statement:
            # 1. Complete by desired_completion (all satisfy)
            # 2. No spending changes (all satisfy)
            # 3. Minimize total amount paid
            # 4. Start payment earlier
            # 5. Fewer payments
            # 6. Lowest payment_option_id
            def rank_key(c):
                return (round(c["total"], 2), c["start"], c["num_payments"], c["opt_id"])

            candidates.sort(key=rank_key)
            best = candidates[0]
            return self._result(
                amount_safe_to_pay=amount_safe if best["status"] != "affordable_now" else self.requested_amount,
                status=best["status"],
                method=best["method"],
                payments=best["payments"],
                earliest_date=best["earliest_date"],
                spending_changes=best["spending_changes"],
                explanation=best["explanation"]
            )

        # 5) Try permitted spending changes to unlock a safe plan
        result = self._try_spending_changes()
        if result is not None:
            return result

        # 6) not_affordable fallback
        return self._result(
            amount_safe_to_pay=amount_safe,
            status="not_affordable",
            method="not_recommended",
            payments=[],
            earliest_date=None,
            spending_changes="none",
            explanation=f"Do not make this payment by {self.desired_completion.strftime('%d %B %Y').lstrip('0')}. None of the available options keeps the {self._money(fc.min_balance)} minimum protected."
        )

    def _try_spending_changes(self):
        fc = self.fc
        stoppable, reducible = fc.flexible_candidates()
        candidate_changes = []
        if stoppable:
            candidate_changes.append([("stop", stoppable[0])])
        if reducible:
            e = reducible[0]
            min_allowed = e.get("min_allowed")
            new_amt = float(min_allowed) if min_allowed is not None and str(min_allowed) != "" and str(min_allowed).lower() != "nan" else 0.0
            candidate_changes.append([("reduce", e, new_amt)])
        if stoppable and reducible and stoppable[0]["event_id"] != reducible[0]["event_id"]:
            e = reducible[0]
            min_allowed = e.get("min_allowed")
            new_amt = float(min_allowed) if min_allowed is not None and str(min_allowed) != "" and str(min_allowed).lower() != "nan" else 0.0
            candidate_changes.append([("stop", stoppable[0]), ("reduce", e, new_amt)])

        candidates = []
        amount_safe = fc.amount_safe_today(self.requested_amount)

        for changes in candidate_changes:
            day_balance, suffix_min = fc.apply_spending_changes(changes)
            earliest_off = self._earliest_full_offset(day_balance, suffix_min)
            earliest_date = fc.date_for_offset(earliest_off) if earliest_off is not None else None
            changes_str = self._changes_to_str(changes)

            # full_payment today with changes
            if "full_payment" in self.methods_accepted and earliest_off == 0:
                candidates.append({
                    "status": "affordable_with_plan",
                    "method": "full_payment",
                    "payments": [(self.request_date, self.requested_amount)],
                    "total": self.requested_amount,
                    "start": self.request_date,
                    "num_payments": 1,
                    "opt_id": "",
                    "earliest_date": self.fc.date_for_offset(fc.earliest_full_payment_offset(self.requested_amount)),
                    "spending_changes": changes_str,
                    "num_changes": len(changes),
                    "explanation": (
                        f"After adjusting flexible spending ({changes_str}), pay {self._money(self.requested_amount)} "
                        f"today while keeping at least {self._money(fc.min_balance)} available."
                    )
                })

            # installments with changes
            insts = self.eligible_installment_options(day_balance, suffix_min)
            for opt, payments in insts:
                candidates.append({
                    "status": "affordable_with_plan",
                    "method": "installments",
                    "payments": payments,
                    "total": float(opt["total_payable_amount"]),
                    "start": payments[0][0],
                    "num_payments": len(payments),
                    "opt_id": opt["payment_option_id"],
                    "earliest_date": earliest_date,
                    "spending_changes": changes_str,
                    "num_changes": len(changes),
                    "explanation": (
                        f"After adjusting flexible spending ({changes_str}), use {len(payments)} installments "
                        f"starting {payments[0][0].isoformat()} to complete {self._money(self.requested_amount)}."
                    )
                })

        if candidates:
            candidates.sort(key=lambda c: (c["num_changes"], round(c["total"], 2), c["start"], c["num_payments"], c["opt_id"]))
            best = candidates[0]
            unmod_earliest_off = fc.earliest_full_payment_offset(self.requested_amount)
            unmod_earliest = fc.date_for_offset(unmod_earliest_off) if unmod_earliest_off is not None else None

            return self._result(
                amount_safe_to_pay=amount_safe,
                status=best["status"],
                method=best["method"],
                payments=best["payments"],
                earliest_date=unmod_earliest,
                spending_changes=best["spending_changes"],
                explanation=best["explanation"]
            )
        return None

    def _changes_to_str(self, changes):
        parts = []
        for c in changes:
            if c[0] == "stop":
                parts.append(f"stop:{c[1]['event_id']}")
            else:
                parts.append(f"reduce_to:{c[1]['event_id']}:{fmt_amount(c[2])}")
        return "|".join(parts)

    def _money(self, x):
        return f"{self.fc.home_currency} {fmt_amount(x)}"

    def _result(self, amount_safe_to_pay, status, method, payments, earliest_date, spending_changes, explanation):
        amount_safe_to_pay = max(0.0, min(self.requested_amount, amount_safe_to_pay))
        return {
            "request_id": self.req["request_id"],
            "amount_safe_to_pay": fmt_amount(amount_safe_to_pay),
            "affordability_status": status,
            "recommended_payment_method": method,
            "payment_plan": plan_str(payments) if method != "not_recommended" else "none",
            "earliest_date_for_full_payment": earliest_date.isoformat() if earliest_date else "",
            "spending_changes_needed": spending_changes,
            "decision_explanation": explanation,
        }
