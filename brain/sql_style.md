# SQL Style  (Layer 1 — brain)

How the agent must *render* SQL so that (a) results are correct, (b) results are **comparable** run-to-run and
against golden answers, and (c) output is self-describing. Everything here that is mechanical is **enforced by
`tools/lint_sql.py`** — each linter finding cites the section below it enforces.

The examples target the fictional "Acme" schema. Adapt to your columns.

---

## §A — Scope & joins (correctness)

- Every query touching `dim_customer_latest` carries the mandatory scope filters (`is_test = FALSE`,
  `is_fraud = FALSE`) — see `glossary.md: Mandatory scope`.
- Every fact table is bridged to the dimension on `customer_id` (mandatory bridge). No fact-to-fact joins.
- Prefer a small CTE that builds the scoped customer set once, then join facts to it.

## §B — Counting (correctness + fan-out safety)

- **Count the entity, distinctly:** `COUNT(DISTINCT customer_id)`. Never `COUNT(*)` (fan-out-unsafe on the
  multi-row fact tables) — the linter WARNs on `COUNT(*)`.
- **Never `COUNTIF(...)`** for entity counts — it counts *rows*, not distinct customers. The linter WARNs.
- **Per-group subset count, keeping zero-buckets:** to count "customers where flag X, by segment", do **not**
  put the flag in a `WHERE` next to a dimension `GROUP BY` — that silently drops segments with zero matches.
  Instead:

  ```sql
  SELECT segment,
         COUNT(DISTINCT IF(is_active_month, customer_id, NULL)) AS active_customers
  FROM ...
  GROUP BY segment
  ```

  This keeps every segment (including zeros) and stays distinct + fan-out-safe. The linter WARNs when a
  subset flag is filtered in `WHERE` under a dimension `GROUP BY`.

  > **Exception:** when the `GROUP BY` grain is itself a time period (month/year), a flag-in-`WHERE` is the
  > correct "active within the period" cohort pattern and is *not* flagged.

## §C — Ratios & derived metrics

- Use safe division (`SAFE_DIVIDE(num, den)` on BigQuery; `NULLIF(den,0)` elsewhere) — never a bare `/`.
- Suffix derived columns by family: `_rate`, `_share`, `_growth`, `_per_<x>`, or a `pct_`/`avg_` prefix.
- A ratio column is exempt from the money/count suffix checks below.

## §D — Output shape & naming

- **snake_case** output column names, always aliased (`... AS active_customers`).
- **Role-based suffixes:**
  - customer/entity counts → `*_customers` (or `num_*`)
  - money sums → `*_revenue`
  - the linter WARNs when a count/money aggregate is aliased without the matching suffix.
- One row per group; dimension columns first, then metrics.
- Order deterministically (`ORDER BY` the dimension keys) so output is stable across runs.

## §E — Determinism (so eval comparisons are meaningful)

- Floating-point `SUM` over a large table is **not** bit-reproducible — the same query can return
  `1234.5600000001` vs `1234.56` across runs/engines. Therefore:
  - round money at the *output* only when presenting, and
  - the eval comparator (`eval/lib/comparator.py`) compares within a **relative tolerance**, keyed by the
    dimension columns — never an exact string diff of rounded floats. Write SQL that a tolerant comparator
    can match: stable grouping keys, stable ordering, named columns.
- Avoid `LIMIT` without `ORDER BY` (non-deterministic sample).
- Avoid `SELECT *` in the final projection — name every output column.

---

## Why these are gates, not just guidance

Anything in §A, §B, §D that is mechanically checkable is implemented in `tools/lint_sql.py` as an `ERROR`
(block) or `WARN` (surface). Prose here is the *explanation*; the linter is the *enforcement*. If you add a
rule here that can be checked, add the check there too and cite this section in the finding.
