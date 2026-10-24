# Buy or Wait? — Solution

Deterministic, rule-based financial-affordability engine. No LLM calls are used to
score `dataset/requests.csv` (see `evaluation/usage_report.md`).

## Run

### 1. Interactive Web Application & API (Port 5176)

```bash
python server.py
```
Open **[http://localhost:5176](http://localhost:5176)** in your browser for the full executive intelligence suite, including:
- **Executive Telemetry & KPI Deck**: Total capital analyzed, status distributions, and safety ratios.
- **Decision Explorer**: Interactive search and deep-dive flyout across all 250 purchase requests.
- **90-Day Cash-Flow Runway**: Interactive SVG liquidity timeline with reserve waterlines and recurring cash drivers.
- **What-If Purchase Simulator**: Real-time evaluation of arbitrary purchase scenarios.
- **Sample Benchmark & Accuracy**: Side-by-side comparison against the 25 ground-truth worked examples.
- **Currency Matrix**: Shortest-path BFS exchange converter across USD, EUR, INR, IDR, and ZAR.

### 2. Batch Pipeline CLI

```bash
python main.py
```

Writes `output.csv` to the repository root with one evaluated row per request in `dataset/requests.csv` (250 rows).

## Evaluate

```bash
python evaluation/main.py
```

Reports `affordability_status` / `recommended_payment_method` accuracy against
`dataset/sample_requests.csv` (the 25 organizer-provided worked examples), and
validates the full `output.csv` against the schema/invariants in
`problem_statement.md` (bounds, valid enums, installment-plan-matches-option,
row count).

## Design

- `code/engine.py`
  - `Data`: loads all `dataset/*.csv`, fills the 16 blank `financial_events.amount`
    cells using amounts transcribed from the linked images in
    `dataset/media/images/` (see `IMAGE_DERIVED_AMOUNTS`), and does light,
    conservative parsing of `messages.csv` to adjust projected salary
    amounts/dates or cancel/delay a directly-linked event. Embedded instructions
    in message/image text are never executed — only `(amount, currency, date)`
    facts are extracted and applied to the matching financial concept.
  - `RateGraph`: converts amounts between currencies using
    `exchange_rates.csv`, with a graph/BFS fallback for currency pairs that
    require an intermediate hop (e.g. INR -> USD -> EUR -> ZAR).
  - `UserForecast`: reconstructs a user's daily cash-flow forecast for the 90
    days following `request_date`:
    - Explicit future events (`scheduled`/`pending` debits, confirmed income)
      inside the window are included directly; pending *credits* are ignored
      per the spec, and `cancelled`/`failed`/`unrealized` rows are dropped.
    - Recurring **singular monthly** items (salary, rent, education fee,
      debt payment, subscriptions) are detected from history (>=2 months of
      activity, ~30 day interval) and projected forward at the same interval
      and amount.
    - Recurring **frequent variable essential spending** (multiple
      transactions/month in one category, e.g. groceries/dining/transport) is
      aggregated per historical month and forecast as one conservative lump
      sum per month (the max of the last three observed months), to avoid
      compounding transaction-level noise while still forecasting essential
      spending conservatively per the spec.
  - `amount_safe_today` / `earliest_full_payment_offset`: derived from the
    forecast's day-by-day balance and its suffix-minimum array (a one-time
    payment made today shifts every future balance by the same constant, so
    the safe amount is exactly `min_future_balance - minimum_balance_to_keep`,
    clamped to `[0, requested_amount]`).
- `code/decide.py`
  - Builds the eligible, safe candidate plans (`full_payment` today,
    `installments` matching a supplied `request_payment_options.csv` row,
    `partial_payment`, `wait`) restricted to the methods in
    `payment_methods_user_will_consider` and `max_installment_months`, ranks
    them per the "Choosing Between Safe Plans" rules (completes by deadline >
    no spending changes > minimize total paid > start earlier > fewer
    payments > lowest `payment_option_id`), and only falls back to permitted
    spending changes (`stop:`/`reduce_to:` on flexible, non-protected
    categories) when no unmodified plan is safe.
- `code/main.py`: entry point, writes `output.csv`.
- `code/evaluation/`: evaluation workflow + token/cost report.

## Known limitations / assumptions (documented for transparency)

- `financial_profiles.current_available_balance` is treated as the balance at
  the *start* of `request_date` (each of the 275 users in this dataset maps to
  exactly one request).
- Message parsing is intentionally conservative/regex-based rather than a full
  NLP pipeline; it captures the clear "salary changed to X, effective Y" /
  "cancelled" / "delayed to Y" patterns in this dataset but will miss more
  exotic phrasings.
- The monthly-aggregation heuristic for variable essential spending (median
  interval detection, "last 3 months, take the max") is a reasonable, declared
  approximation of "forecast essential variable spending conservatively" — the
  exact aggregation an organizer's hidden reference implementation uses may
  differ, which is the main source of residual error against
  `sample_requests.csv` (see `evaluation/main.py` output for current accuracy).
