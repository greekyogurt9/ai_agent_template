# Business Glossary  (Layer 1 — brain)

**The single rulebook.** Every canonical metric and identity rule lives here and *only* here. Do not restate
any of these in the prompt, the agent code, or a second doc — if a rule is duplicated it will drift, and the
agent will apply the stale copy and produce a confidently-wrong number.

The examples below are for the fictional "Acme" company. **Replace every rule with yours.** Keep each rule
*precise and checkable* — a rule the linter can enforce (see `sql_style.md` and `tools/lint_sql.py`) is worth
ten vibes.

> **Convention:** each rule names the columns it touches, but never the *values* of a categorical column —
> the agent fetches those live with `tools/show_values.sh`. Example: this glossary says "filter on the plan
> column," not "`plan = 'PRO'`", because the exact string is discovered live.

---

## Identity — what we count

- **Default entity: `customer`**, counted as `COUNT(DISTINCT customer_id)`.
- `customer_id` is the canonical key on `dim_customer_latest` (unique, non-null there) and the join key on
  the fact tables.
- **Funnel / pre-activation exception:** early-funnel rows can have a NULL `customer_id`. For onboarding /
  pre-activation counts, count `signup_id` instead — **and state explicitly** that the count is on signups.

---

## Mandatory scope (applied by default, unless the question says otherwise)

These filters are ON by default. They are enforced as **hard gates** in `tools/lint_sql.py`.

1. **Exclude test/internal accounts.** Every query that touches `dim_customer_latest` must filter
   `is_test = FALSE`. (Fraud/test rows exist only on the dimension.)
2. **Exclude a fraud-flagged customer.** Filter `is_fraud = FALSE` on the dimension.
3. **Mandatory bridge.** A fact table (`fct_orders_daily`, `fct_product_usage_monthly`) must be joined to
   `dim_customer_latest` on `customer_id` so it inherits the scope above. Summing a fact table *without* the
   bridge counts out-of-scope customers → wrong number.

> Onboarding-funnel queries (counting `signup_id` on pre-activation milestones) are the one sanctioned
> exception to the bridge rule — they legitimately live before the dimension is populated.

---

## Metrics

### Revenue (the headline money metric)
- **Definition:** `SUM(order_amount)` from `fct_orders_daily`, bridged to the dimension (scope above).
- **No extra filter** by default — total revenue is *all* channels/order types.
- **A channel-specific cut** (e.g. "online revenue") adds a filter on the `channel` column — fetch its real
  values with `show_values` first; do not assume the string.
- Output money columns are suffixed `*_revenue` (see `sql_style.md`).

> **The over-filtering trap:** the #1 metric error is adding a filter the question didn't ask for (e.g.
> restricting to one channel when asked for total). Plain "revenue" = no channel filter. Only narrow when the
> question narrows.

### Active customer
- **Definition:** a customer with `revenue_last_365d > 0` on `dim_customer_latest`.
- Use the precomputed column — do **not** re-derive "active" from a last-order-date alone (a customer can
  have an old last-order date but recent revenue via another path). The precomputed flag is the SSOT.
- "Active in month M" is a *different* question — use the monthly flag on `fct_product_usage_monthly`
  (`is_active_month`), evaluated within each month (a period grain, not a snapshot).

### Monthly active / engagement
- `fct_product_usage_monthly.is_active_month` = the customer had ≥1 qualifying action that month.
- Do not conflate with feature-usage flags on the same table; each flag means one specific thing — check the
  live schema description with `show_schema` if unsure what a flag means.

---

## Grain guidance

- **Per-customer current state / lifetime** → `dim_customer_latest`.
- **Revenue or volume over time** → `fct_orders_daily` (day grain; aggregate to the period asked).
- **Engagement / feature adoption over time** → `fct_product_usage_monthly` (month grain only).
- Never join two fact tables directly; route both through the dimension.

---

## Dates & windows

- If a question implies a date window but doesn't give exact bounds, **STOP and confirm the range** before
  writing SQL. Do not silently invent a window.
- When you do assume a window, **state it in the answer** ("assumed calendar year 2025, Jan 1 – Dec 31").

---

## How to extend this file

When the eval surfaces a *systematic* error (the agent keeps getting a class of questions wrong):

1. Find the **root** — an ambiguous definition, a missing default, a rule stated only vaguely.
2. Fix it **here**, in one place, precisely.
3. If the rule is mechanically checkable, also add a gate in `tools/lint_sql.py` that cites this section.
4. Re-run the component eval for the affected decision; then a full eval; snapshot both.

Do not patch individual wrong answers — fix the rule that generates the class.
