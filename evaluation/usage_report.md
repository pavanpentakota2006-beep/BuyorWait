# Token Usage and Cost Report

## Final full-dataset run (the one that produced `output.csv`)

This solution is a **deterministic, rule-based engine** (see `code/engine.py` and
`code/decide.py`). It does **not** call any LLM/VLM API to score `dataset/requests.csv`.
The problem statement fully specifies the decision rules (90-day safety check, plan
ranking, currency conversion, spending-change eligibility), so a deterministic
implementation is reproducible, auditable, and matches the brief's "keep behavior
deterministic where possible" guidance.

| Metric | Value |
|---|---|
| Model provider | (none used for scoring) |
| Model name | (none) |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens / request | 0 |
| Estimated total cost | $0.00 |
| Estimated cost / request | $0.00 |

## Where a model *was* used (development only, not part of the scored run)

During development, a multimodal chat assistant (Claude, used interactively through
the Claude.ai chat interface — see `log.txt`) was used to **read the 16 receipt /
payslip / bill images** referenced by `dataset/images.csv` for the financial events
that ship with a blank `amount` (see `IMAGE_DERIVED_AMOUNTS` in `code/engine.py`).
This is a one-time, offline data-reconstruction step, not a per-request inference
call, and it produced no billable Anthropic API token usage (it was an interactive
chat session, not an API call). The 16 extracted amounts are hard-coded as
reconstructed *input data* (not as answers/labels for any request) in
`code/engine.py`, exactly the way a human analyst would transcribe a number off a
scanned document once.

If a future revision wants those 16 amounts extracted programmatically via the
Anthropic API (e.g. `claude-sonnet-4-6` vision) instead of at development time, the
per-image cost would be roughly:

| Model | Images | Est. input tokens/image | Est. output tokens/image | Est. cost/image | Est. total (16 images) |
|---|---|---|---|---|---|
| claude-sonnet-4-6 (vision) | 16 | ~1,200 | ~50 | ~$0.0045 | ~$0.07 |

This was not required for the submitted `output.csv`, since the amounts are already
resolved as static input data.

## Full-dataset run stats

- Requests scored: 250 (`dataset/requests.csv`)
- Wall-clock run time: < 5 seconds on a single CPU core
- External API calls made during the run: 0
- Compute cost: negligible (local CPU only)
