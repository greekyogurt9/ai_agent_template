# SWAP_DATASETS.md — make this template yours without breaking it

> **Goal:** point this agent at YOUR tables, write YOUR glossary, and get
> trustworthy answers — without the linter, the prompt, or the eval fighting you.
>
> **Companion docs:** `GETTING_STARTED.md` is the ordered checklist,
> `ARCHITECTURE.md` is the why. This file is the **dataset-swap path**: what to
> change, in what order, what breaks if you skip it, and how to verify each step.

---

## 0. How long does this take? (TL;DR)

| Path | Time | What you get |
|---|---|---|
| **Smoke test** (warehouse wired + 3 tables described + 5 goldens) | **45–90 min** | `make check` green, first `python -m agent.agent "..."` answer works |
| **Standard swap** (3–5 tables, full glossary, 10–20 goldens, gates tuned) | **4–6 hours (~half a day)** | trusted Q&A loop with eval score + revert point |
| **Production-hardened** (15–20+ goldens, component evals, deck/deep-dive) | **1–2 days** | rollout-ready with version memory |

**Assumptions:** you know your schema, your warehouse CLI works (`bq` /
`snowsql` / `psql`), and your LLM CLI is logged in. The bottleneck is almost
always **Step 2 (glossary)** — writing precise business rules — not code.

**Time breakdown (standard swap, 3–5 tables):**

| Step | Time | Why |
|---|---|---|
| 0 — Engines + config | 15–30 min | install/auth warehouse CLI + LLM CLI |
| 1 — `semantic_model.yaml` + `policy:` | 30–45 min | pick smallest sufficient table set |
| 2 — `glossary.md` | 45–60 min | highest-leverage file; be precise |
| 3 — `sql_style.md` | 20–30 min | counting / naming / ratios |
| 4 — `lint_sql.py` + `pii_guard.py` | 30–45 min | gates follow the policy; selftest green |
| 5 — `show_schema.sh` / `show_values.sh` | 20–30 min | uncomment your warehouse block, test live |
| 6 — `golden_cases.yaml` + route cases | 45–60 min | 10–20 hand-verified Q→SQL pairs |
| 7 — Trust loop (`check` → `component` → `eval`) | 30–60 min | baseline score + snapshot |
| 8 — Docker / budgets / commit | 15–30 min | env parity + version memory |

> **Windows note:** this repo's `Makefile` calls `python3`. On Windows use
> `python` instead (e.g. `python -m agent.config`), or run everything inside
> Docker (`docker compose exec ai-agent ...`). The code itself is OS-agnostic.

---

## 1. The three rules that keep a swap from breaking

1. **Never store what you can look up.** Column names and category values are
   fetched **live** via `tools/show_schema.sh` and `tools/show_values.sh`.
   Do NOT list columns, types, or enum strings in `semantic_model.yaml` or the
   glossary. If you do, they *will* drift and the agent *will* hallucinate.
   - Glossary says: *"filter on the `channel` column"* — never
     *"`channel = 'ONLINE'`"*. The exact string is discovered live.
2. **One home per rule.** `brain/glossary.md` is the single rulebook.
   Do NOT restate a metric/scope definition in the prompt, the agent code, or a
   second doc. `agent/prompt.py:verify_brain_is_live()` **fails the build** if
   a copy of any brain file appears inside `agent/` — by design.
3. **A rule that can be a gate should never live only in a prompt.** Every
   high-confidence, mechanically-checkable rule gets a check in
   `tools/lint_sql.py` (which cites the brain section it enforces) plus PII in
   `tools/pii_guard.py`. Prose is hope; gates are guarantees.

Break any of these and the swap "works" in demo and fails on real questions.

---

## 2. What actually breaks on a naive swap (read this first)

| # | Breakage | Symptom | Fix (this doc) |
|---|---|---|---|
| 1 | **Stale lint policy** — `semantic_model.yaml` updated but linter still enforces Acme `dim_customer_latest` / `is_test` / `order_amount` | every query blocked with false `fact_unbridged` / `missing_test_scope` ERRORs | Step 1: edit the `policy:` block — `tools/lint_sql.py` reads it automatically |
| 2 | **Hardcoded warehouse path** — `agent/review.py` / `eval/run_eval.py` assumed BigQuery | dry-run / eval execute fails on Snowflake/Postgres | Step 0+5: set `WAREHOUSE_ENGINE`; both modules now dispatch on it (BigQuery / Snowflake / Postgres) |
| 3 | **Stored schema** — columns/values pasted into brain files | `column not found` / wrong category string (`'ACTIVE'` vs `'Active'`) | Step 5: wire `show_schema.sh` / `show_values.sh`, keep brain structure-only |
| 4 | **Duplicated rules** — metric defined in glossary AND prompt/agent | agent applies the stale copy → confidently-wrong number | Step 2: glossary only; never copy into `agent/` |
| 5 | **Untuned PII list** — Acme `PII_COLUMNS` left as-is | real PII leaks through, or safe IDs (`order_id`) blocked | Step 4: edit `pii_guard.py` allow/block lists |
| 6 | **No goldens** — old Acme `golden_cases.yaml` kept | eval scores garbage; can't tell if a change helped | Step 6: rewrite 10–20 cases with `${PROJECT}.${DATASET}` placeholders |

---

## 3. Prerequisites (Step 0 — engines + `agent/config.py`)

You need two engines (Layer 3). The template is engine-agnostic; both
call-sites dispatch on `WAREHOUSE_ENGINE`.

- **Warehouse CLI with dry-run:**
  - BigQuery → `bq query --dry_run`
  - Snowflake → `snowsql` with `EXPLAIN`
  - Postgres → `psql` (`$PGCONN`) with `EXPLAIN`
- **LLM you can call headless:** a CLI in print mode (keyless, simplest) or an
  SDK client. Only `agent/agent.py:_invoke()` changes when you swap these.

**Do this:**

1. Set env (or edit the defaults in `agent/config.py` / `docker-compose.yml` —
   all four must agree):
   ```bash
   # BigQuery example
   export WAREHOUSE_ENGINE=bigquery
   export WAREHOUSE_PROJECT=your-project
   export WAREHOUSE_DATASET=your_dataset
   export AGENT_MODEL=your-model-id
   export AGENT_LLM_CLI=llm            # your headless LLM command
   export MAX_RUN_USD=3.0
   export MAX_SESSION_USD=50.0
   ```
   Postgres adds `export PGCONN="postgresql://user@host/db"`.
2. Verify:
   ```bash
   python -m agent.config    # Windows; Mac/Linux: python3 -m agent.config
   python -m agent.prompt    # asserts brain-is-live + prints prompt size/hash
   ```
   Expect `brain present OK` and `brain is live: OK`. If it reports
   `MISSING`, you deleted/renamed a brain file. If it raises
   `Brain file copied into agent/`, delete the copy inside `agent/`.

---

## 4. Step 1 — Describe YOUR tables (`brain/semantic_model.yaml`)

**Pick the smallest set of tables that answers most questions** (3–5 to start).
Restraint is a feature — fewer tables = less routing ambiguity. The shipped
example is fictional Acme (`dim_customer_latest` + two facts).

For each table record **structure only** — grain, keys, routing, joins, caveats:

```yaml
warehouse:
  engine: bigquery
  project: your-project
  dataset: your_dataset

entity:
  name: patient              # YOUR entity (customer | member | order | patient …)
  key: patient_id            # canonical key — COUNT(DISTINCT <key>)

policy:                      # ← PORTABILITY: the linter reads THIS block
  dim_table: dim_patient_latest
  fact_tables:
    - fct_visits_daily
    - fct_labs_monthly
  entity_key: patient_id     # must match entity.key above
  scope_columns:             # = FALSE filters required when dim is touched
    - is_test
    - is_fraud
  subset_flags:              # flag-in-WHERE under dim GROUP BY drops zero-buckets
    - is_active_month
  money_columns:             # SUM(...) on these must alias *_revenue
    - charge_amount

tables:
  dim_patient_latest:
    grain: one row per patient (current state)
    primary_key: patient_id
    join_key: patient_id
    routing: >
      Pick this for WHO the patient is — demographics, cohort flags,
      and precomputed lifetime metrics. Scope/identity bridge for all facts.
    provides: [attributes, lifecycle timestamps, scope flags]
    caveats: [primary key unique + non-null here]

  fct_visits_daily:
    grain: one row per patient per day per department
    join_key: patient_id
    routing: Pick this for visit volume / charges over time. Aggregate always.
    joins:
      - to: dim_patient_latest
        on: patient_id
        mandatory: true
        why: Inherits scope (test/fraud exclusion). Sums without the bridge are wrong.
    caveats: [fan-out — COUNT DISTINCT; department is categorical — show_values first]
```

**Rules:**

- `policy.entity_key` MUST equal `entity.key`. `policy.dim_table` /
  `fact_tables` MUST equal the keys under `tables:`.
- If a fact gives a different answer with vs without the dim join, that join is
  **mandatory** — record it here AND enforce it in the linter (Step 4, automatic
  once `policy:` is right).
- No fact-to-fact joins. Everything routes through the dimension.
- Never list columns/types/values here (see rule #1 above).

**Verify:** `python -m agent.prompt` still prints `brain is live: OK`
(the hash will change — that is expected; same hash = same brain).

---

## 5. Step 2 — Write YOUR business rules (`brain/glossary.md`)

Highest-leverage file. Capture the **non-obvious meaning** a new analyst gets wrong:

- **Identity** — default entity + canonical key; sanctioned exceptions
  (e.g. Acme counts `customer_id`, but pre-activation funnel counts `signup_id`
  and must say so).
- **Mandatory scope** — filters ON by default (Acme: `is_test = FALSE`,
  `is_fraud = FALSE` + mandatory dim bridge). Name YOUR columns; keep the list
  identical to `policy.scope_columns` in Step 1.
- **Metric definitions** — exact formula, table, grain, default filters.
  Acme revenue = `SUM(order_amount)` from `fct_orders_daily`, bridged, **no**
  channel filter unless asked (the over-filtering trap). Active = predefined
  column, not re-derived.
- **Grain guidance** — which table for which question; never join facts directly.
- **Dates** — if a window is implied but not exact, STOP and confirm; if you
  assume one, state it in the answer.

**Template for each rule:**

```markdown
### <Metric> (the headline <money|count|rate> metric)
- **Definition:** `<AGG(col)>` from `<fact>`, bridged to `<dim>` (scope above).
- **No extra filter** by default — plain "<metric>" = no narrowing.
- **A narrowed cut** adds a filter on `<categorical col>` — fetch values with
  `show_values` first; do not assume the string.
- Output columns suffixed `*_<family>` (see `sql_style.md`).
```

Keep each rule **precise and checkable**. A rule the linter can enforce is worth
ten vibes. When eval later surfaces a systematic error, fix it HERE once —
never patch individual answers.

---

## 6. Step 3 — Set YOUR SQL house style (`brain/sql_style.md`)

How queries render so results are correct, comparable, and deterministic:

- **§A Scope & joins** — mandatory scope filters + mandatory bridge; prefer a
  small CTE building the scoped set once, then join facts to it.
- **§B Counting** — `COUNT(DISTINCT <your entity_key>)`, never `COUNT(*)` or
  `COUNTIF(...)` for entity counts. Per-group subset counts use
  `COUNT(DISTINCT IF(<flag>, <key>, NULL))` to keep zero-buckets
  (flag-in-`WHERE` under a dimension `GROUP BY` silently drops them; time-grain
  `GROUP BY` is the sanctioned exception).
- **§C Ratios** — safe division (`SAFE_DIVIDE` / `NULLIF(den,0)`); suffix
  `_rate` / `_share` / `_growth` / `_per_<x>` / `pct_` / `avg_`.
- **§D Naming** — snake_case, always aliased; counts → `*_customers` (or `num_*`),
  money → `*_revenue`. Rename the families if your entity/money differ
  (e.g. `*_patients`, `*_charges`) — and mirror the rename in `policy:` +
  linter (Step 4).
- **§E Determinism** — `ORDER BY` dimension keys, no bare `LIMIT`, no
  `SELECT *`, money rounded only at presentation. Float sums are not
  bit-reproducible — the comparator tolerates it, so write matchable SQL
  (stable keys, ordering, named columns).

Whatever you state as a mechanical rule here, enforce in Step 4.

---

## 7. Step 4 — Turn rules into gates (`tools/lint_sql.py`, `tools/pii_guard.py`)

**`lint_sql.py` — you (usually) only edit YAML.** It loads `policy:` from
`brain/semantic_model.yaml` at import and enforces: unbridged fact (ERROR),
missing scope filter per `scope_columns` (ERROR), `COUNT(*)`/`COUNTIF` (WARN),
subset-flag-in-`WHERE` under dim `GROUP BY` (WARN), PII via `pii_guard.py`
(ERROR), naming (`*_customers`/`*_revenue`, WARN). Missing `policy:` or missing
PyYAML → falls back to Acme defaults (documented in-file), so old checkouts
keep working.

```bash
python tools/lint_sql.py --selftest     # must print SELFTEST: PASS
echo "SELECT 1" | python -m agent.review  # gate ladder smoke test
```

> Keep checks **conservative**: only flag high-confidence violations. A noisy
> gate trains people to ignore the linter. Uncertain = `WARN`, never `ERROR`.
> Each finding cites its brain section — the brain stays the single home.

**`pii_guard.py` — you MUST edit the lists.** Single source of truth for
"what can never leave the warehouse" (linter + review both delegate here):

```python
PII_COLUMNS = {"email", "phone", ...}   # exact columns — never output
PII_PATTERNS = (r"e?mail", r"phone", ...)  # tight substrings — keep narrow
PII_ALLOW = {"customer_id", "order_id", ...}  # safe IDs that look PII-ish
```

```bash
python tools/pii_guard.py --selftest    # must print PII SELFTEST: PASS
```

Two checks: PII column in SQL text (pre-run) + PII-looking header in executed
results (catches `SELECT *` surprises).

---

## 8. Step 5 — Point introspection at YOUR warehouse (`tools/show_*.sh`)

Uncomment YOUR warehouse block (BigQuery / Snowflake / Postgres snippets are
in-file), keep output shapes stable (`name,type` and `value,n`):

```bash
tools/show_schema.sh your_dim_table
tools/show_values.sh your_dim_table your_status_column
```

Once these work, the agent can never hallucinate a column or category value.
For very large tables, prefer a sampled/partition-restricted `show_values`
variant (comment in-file).

---

## 9. Step 6 — Write YOUR goldens (`eval/golden_cases.yaml` + route cases)

10–20 **question → hand-verified reference SQL** cases. Tier `core` (fast smoke,
every change) vs `extended` (nightly full). Use `${PROJECT}.${DATASET}`
placeholders — `eval/run_eval.py:_execute()` substitutes your
`agent/config.py` values and dispatches on `WAREHOUSE_ENGINE`:

```yaml
cases:
  - id: total_active_patients
    tier: core
    question: "how many active patients do we have?"
    reference_sql: |
      SELECT COUNT(DISTINCT patient_id) AS active_customers
      FROM `${PROJECT}.${DATASET}.dim_patient_latest`
      WHERE is_test = FALSE AND is_fraud = FALSE
        AND revenue_last_365d > 0
```

Also update `eval/lib/component_eval.py:ROUTE_CASES` (question → expected table)
so `make component` isolates routing on YOUR tables.

The comparator (`eval/lib/comparator.py`) is float-tolerant, name-insensitive,
order-insensitive **on purpose** — never string-diff rounded floats. Self-test:

```bash
python -m eval.lib.comparator --selftest
```

---

## 10. Step 7 — Run the trust loop

```bash
python -m eval.run_eval check              # FREE: brain-live + all selftests
python -m eval.run_eval component route    # CHEAP: one decision in isolation
python -m eval.run_eval run baseline       # FULL: snapshot + goldens + score
# or via Make on Mac/Linux: make check / make component / make eval RUN=baseline
```

Then **read failures → find the systematic cause → fix the root in `brain/` →
re-run.** One structural fix beats fifty patches. Every full run snapshots
`brain/` to `eval/runs/<id>/brain/` + appends `ledger.jsonl` (tagged with brain
hash), so:

```bash
python -m eval.lib.snapshot list           # runs + brain hashes
python -m eval.lib.snapshot diff a b       # what changed between runs
python -m eval.lib.snapshot restore <id>   # revert brain to last-good
```

Commit after a run you like — git history + ledger = permanent version memory.

End-to-end ask (saves `agent/runs/<slug>_<date>.md` + cost log):

```bash
python -m agent.agent "how many active patients do we have?"
```

---

## 11. Step 8 — Docker, budgets, deck (finish portable)

- **`docker-compose.yml`:** mirror your env (`WAREHOUSE_ENGINE/PROJECT/DATASET`,
  `AGENT_MODEL`, budgets) so `docker compose exec ai-agent ...` matches local.
  No code install needed beyond `docker compose up --build -d`.
- **Budgets (`agent/config.py`):** `MAX_RUN_USD` warns per answer,
  `MAX_SESSION_USD` hard-stops the session (`BudgetExceeded`); every run appends
  `agent/runs/cost_log.tsv`. Set these before handing the agent to others.
- **Outward allowlist:** `OUTWARD_ALLOWLIST` gates anything leaving the system
  (email/Slack/deck delivery). Keep tight; deck mode supports dry-run.
- **Deck assets (`templates/Template.pptx`):** generic placeholder — replace
  with your branded `.pptx` (keep filename); the future `create_deck.py`
  clones it. Regenerate via `templates/make_placeholder_deck.py`.

---

## 12. Condensed checklist (copy into your PR)

- [ ] `agent/config.py` + env + `docker-compose.yml` agree (engine/project/dataset/model/budgets)
- [ ] `brain/semantic_model.yaml` — smallest sufficient tables, structure only, `policy:` == `entity`/`tables`
- [ ] `brain/glossary.md` — identity / scope / metrics / grain / dates, stated once, precisely
- [ ] `brain/sql_style.md` — counting entity, money column, suffix families match `policy:`
- [ ] `tools/lint_sql.py --selftest` green (no code edit needed — policy drives it)
- [ ] `tools/pii_guard.py` — PII block/allow lists yours; `--selftest` green
- [ ] `show_schema.sh` / `show_values.sh` — live against YOUR warehouse
- [ ] `eval/golden_cases.yaml` (10–20, `${PROJECT}.${DATASET}`) + `ROUTE_CASES` yours
- [ ] `eval/run_eval check` green; first `run baseline` recorded; snapshot restores
- [ ] First `agent.agent "..."` answer + artifact saved; commit brain + ledger

---

## 13. Troubleshooting — swap failures and fixes

| Symptom | Cause | Fix |
|---|---|---|
| False `fact_unbridged` / `missing_*_scope` ERRORs on YOUR tables | `policy:` still Acme | update `policy:` dim/facts/scope; re-run `--selftest` |
| `column not found` / wrong category string | columns/values pasted in brain | delete from brain; verify `show_schema`/`show_values` live |
| `Brain file copied into agent/` | forked brain copy | delete copy in `agent/`; brain lives in `brain/` only |
| Safe ID blocked as PII (`order_id`) | over-broad pattern, missing allow | add to `PII_ALLOW`, tighten `PII_PATTERNS` |
| Real PII passes the gate | blocklist not updated | add exact column to `PII_COLUMNS` |
| Dry-run fails on Snowflake/PG | `WAREHOUSE_ENGINE` still `bigquery` | set engine; check CLI auth (`snowsql`, `PGCONN`) |
| Eval mismatches on identical-looking money | exact float diff | trust the tolerant comparator; check dimension keys, not strings |
| Score drops after a brain edit | systematic rule regression | `snapshot diff` + `restore <last-good>`, fix root, re-run |
| `make` fails on Windows (`python3` not found) | Windows Store alias | use `python -m ...` directly or Docker exec |

If stuck: `python -m agent.config` → `show_schema` → `lint --selftest` →
`run_eval check`, in that order. The first red step is the root.
