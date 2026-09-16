# Getting Started — adapt this template to your data

Work through these steps **in order**. Each builds on the last. The whole point is that by the end you have a
trustworthy agent for *your* warehouse without having written the hard parts (gates, comparator, snapshot,
trust loop) yourself — you only supplied the knowledge.

Estimated first-pass time: **half a day** for a handful of tables.

---

## Step 0 — prerequisites

You need two engines (Layer 3). The template is deliberately engine-agnostic; you wire them in `config.py`.

- **A warehouse CLI** that runs SQL non-interactively and supports a **dry-run** (validate without running):
  - BigQuery → `bq query --dry_run`
  - Snowflake → `snowsql` / the Python connector with `EXPLAIN`
  - Postgres → `psql` with `EXPLAIN`
- **An LLM you can call headless** — either a CLI (e.g. an agent CLI in `-p`/print mode) or an SDK client.
  Keyless via an existing CLI login is simplest to start; swap to an SDK later — only the invocation layer in
  `agent.py` changes.

Set your identifiers and auth surface in `agent/config.py` (warehouse project/dataset, model id, budgets).

---

## Step 1 — describe your tables (`brain/semantic_model.yaml`)

Pick the **smallest set of tables that answers the majority of questions.** Restraint is a feature — fewer
tables means less routing ambiguity. The example ships with three (a dimension + two fact grains).

For each table record **structure only** — never columns or values (those are fetched live):

- `grain` — what one row means (e.g. "one customer", "one customer × day").
- `keys` — primary key and the join key(s).
- `routing` — one line on when to pick this table.
- `joins` — how it connects to the others, and any **mandatory bridge** (a fact table that must be joined
  through the dimension to inherit scope/identity).
- `caveats` — traps (a known data hole, a grain gotcha).

> Rule of thumb: if a fact tells you the answer changes when you *don't* join the dimension, that join is
> **mandatory** — record it here and enforce it in `lint_sql.py` (Step 4).

---

## Step 2 — write your business rules (`brain/glossary.md`)

This is the highest-leverage file. Capture the **non-obvious meaning** a new analyst would get wrong:

- **Metric definitions** — what *exactly* is "revenue"? Which column, which filter, which grain?
- **Identity** — what is the entity you count (customer? account? order?) and its canonical key?
- **Mandatory scope** — the filters that apply *by default* (exclude test/fraud/internal accounts, a
  segment you always drop unless asked).
- **"Active"** and other status definitions — the precise, checkable rule, not a vibe.
- **Grain choices** — when to use the monthly table vs the daily one.

Keep it a **single rulebook.** Do not restate a rule anywhere else (not in the prompt, not in the agent). If
a rule is repeated in two places, they *will* drift, and the agent will apply the stale one and produce a
confidently-wrong number. One home per rule.

---

## Step 3 — set your SQL house style (`brain/sql_style.md`)

How queries should be *rendered* so results are comparable and deterministic:

- **Counting** — `COUNT(DISTINCT <entity>)`, never `COUNT(*)`; how to count a per-group subset without
  dropping zero-buckets.
- **Ratios** — safe division; suffix conventions (`_rate`, `_share`, `_per_`).
- **Naming** — snake_case output columns with role-based suffixes (`*_customers`, `*_revenue`).
- **Determinism** — avoid patterns whose result varies run-to-run (e.g. summing floats in an order that the
  engine doesn't guarantee — this actually breaks naive eval comparisons; see the comparator in Step 6).

Whatever you can state here as a mechanical rule, you will enforce in Step 4.

---

## Step 4 — turn rules into gates (`tools/lint_sql.py`, `tools/pii_guard.py`)

For every glossary/style rule that is **high-confidence and mechanically checkable**, add a check to the
linter. The template ships with worked examples against the Acme schema — edit them to your columns:

- mandatory scope filter present,
- mandatory bridge join present,
- `COUNT(*)` flagged,
- subset-flag-in-`WHERE`-under-`GROUP-BY` flagged (the zero-bucket trap),
- no PII column in the output (delegated to `pii_guard.py`),
- output naming convention.

List your PII columns/patterns in `pii_guard.py` — this is the one place that answers "what can never leave
the warehouse." Run `python3 tools/lint_sql.py --selftest` to confirm your checks fire on the right cases and
stay silent on clean SQL.

> A check that produces false positives is worse than no check — it trains people to ignore the linter. Keep
> checks **conservative**: only flag high-confidence violations. Everything uncertain is a `WARN`, not an
> `ERROR`.

---

## Step 5 — point the introspection scripts at your warehouse (`tools/show_*.sh`)

Edit `show_schema.sh` and `show_values.sh` to your warehouse CLI (the template has BigQuery / Snowflake /
Postgres snippets — uncomment the one you use). Test them:

```bash
tools/show_schema.sh your_fact_table
tools/show_values.sh your_dim_table your_status_column
```

These are the "never store what you can look up" mechanism. Once they work, the agent can never hallucinate a
column or a category value.

---

## Step 6 — write your goldens (`eval/golden_cases.yaml`)

Write 10–20 **question → known-answer SQL** cases to start. For each: the plain-English question, a
hand-verified reference SQL (the answer you *know* is right), and a tier (`core` for a fast smoke set,
`extended` for the nightly full set).

The comparator (`eval/lib/comparator.py`) is **float-tolerant and column-name-insensitive** on purpose:
warehouse float sums are not bit-reproducible, and the agent may name a column slightly differently than your
reference. It compares *values* within a relative tolerance, keyed by the dimension columns — never a raw
string diff of rounded floats.

---

## Step 7 — run the trust loop

```bash
make check                 # free: structure + dry-run drift + linter self-test
make component             # fast: isolate one decision after a small brain edit
make eval RUN=baseline     # full: snapshot brain, run goldens through the agent, score, record
```

Then **read the diagnostics, find the systematic error, fix the root, repeat.** Every `make eval` snapshots
the brain into `eval/runs/<id>/brain/` and appends the score to the ledger, so:

- you can always see whether a change helped or hurt (the score delta, keyed by brain hash), and
- if a change made things worse, `python3 -m eval.lib.snapshot restore <id>` reverts the brain instantly.

Commit after a run you like — the git history + the ledger are your permanent version memory.

---

## Step 8 (optional) — grow the heavier modes

Once the ask loop is solid, add the analyst-grade modes (stubs referenced in `agent/README.md`):

- **deep dive** — a method doc + `agent/deep_dive.py` that runs a full root-cause investigation (cohort
  analysis, decomposition, survival analysis) and reconciles every segment back to the headline delta.
- **deck** — a method doc + `agent/create_deck.py` that builds a stakeholder deck from the deep dive, scores
  it with a rubric critic until it clears a bar, and delivers it through an allowlisted channel.

Same live-brain + engine + gates pattern — you're only adding the method text and the output format.

---

## The checklist, condensed

- [ ] `config.py` points at your warehouse + LLM, budgets set
- [ ] `semantic_model.yaml` — your smallest sufficient table set, structure only
- [ ] `glossary.md` — every non-obvious rule, stated once
- [ ] `sql_style.md` — counting / ratios / naming / determinism
- [ ] `lint_sql.py` + `pii_guard.py` — your mechanical rules as gates; `--selftest` green
- [ ] `show_schema.sh` / `show_values.sh` — talk to your warehouse
- [ ] `golden_cases.yaml` — 10–20 verified cases
- [ ] `make check` green, first `make eval` recorded and committed
