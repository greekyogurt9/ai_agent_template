# Architecture

How this template is put together, and *why* each piece exists. If `README.md` is the pitch, this is the
blueprint. Nothing here is specific to any real business — the examples use a fictional "Acme" dataset.

---

## 1. The mental model: LLM as salt

A production analytics agent is **not** "an LLM that writes SQL." It is a **deterministic pipeline with an
LLM in exactly two places**:

1. **Reasoning** — turning a fuzzy question into a routing + filtering decision.
2. **A final taste-test** — an optional LLM review of the finished query.

Everything else — what tables exist, what a metric means, how to count, whether the SQL is well-formed,
whether the result matches a known answer — is **code**. The design rule:

> If a step has a correct deterministic answer, do not ask the LLM to guess it. Compute it, look it up, or
> gate it.

This is what keeps the agent trustworthy *and* cheap. Every responsibility you move out of the prompt is one
fewer place the model can silently be wrong.

---

## 2. The four layers

```
┌───────────────────────────────────────────────────────────────────────┐
│ LAYER 1 — BRAIN (single source of truth, read live every run)          │
│   brain/semantic_model.yaml   routing · grain · keys · joins (structure)│
│   brain/glossary.md           metric & identity MEANING (business rules)│
│   brain/sql_style.md          how to render SQL canonically             │
│   tools/show_schema.sh        LIVE column names/types  (never stored)   │
│   tools/show_values.sh        LIVE category values     (never stored)   │
└───────────────────────────────────────────────────────────────────────┘
             ▲ reads live                              ▲ enforced by
             │                                         │
┌────────────┴─────────────────────┐   ┌───────────────┴──────────────────┐
│ LAYER 2 — AGENT (thin orchestr.) │   │ LAYER 1 (cont.) — GATES           │
│   config.py  paths/model/budgets │   │   tools/lint_sql.py   SQL linter  │
│   prompt.py  build prompt (live) │   │   tools/pii_guard.py  PII policy  │
│   agent.py   the ask loop        │   └───────────────────────────────────┘
│   review.py  the gate ladder     │
└────────────┬─────────────────────┘
             │ invokes
             ▼
┌───────────────────────────────────────────────────────────────────────┐
│ LAYER 3 — ENGINES (external, swappable)                                 │
│   your LLM        (CLI or SDK — the reasoning engine)                   │
│   your warehouse  (BigQuery / Snowflake / Postgres — runs the SQL)      │
└───────────────────────────────────────────────────────────────────────┘
             ▲ measured by
             │
┌────────────┴──────────────────────────────────────────────────────────┐
│ LAYER 4 — TRUST HARNESS (dev-time; gates rollout)                       │
│   eval/golden_cases.yaml   question → known-answer SQL (objective)      │
│   eval/lib/comparator.py   float-tolerant result compare               │
│   eval/lib/component_eval  isolate ONE decision (fast signal)          │
│   eval/lib/critic.py       rubric-scored LLM critic (subjective)       │
│   eval/lib/snapshot.py     snapshot brain per run → one-command revert  │
└───────────────────────────────────────────────────────────────────────┘
```

### Why brain and agent are separate

The **brain** is data (YAML + Markdown + two shell scripts). The **agent** is a program. Keeping them apart
means:

- Non-engineers can edit rules (`glossary.md`) without touching Python.
- The agent has **no baked-in knowledge** — `prompt.py` reads the brain from disk on every run and
  `verify_brain_is_live()` *fails the build* if a copy of a brain file ever appears inside `agent/`. A forked
  copy is how a brain goes stale; the template makes that impossible by construction.

### Why schema and values are live, never stored

The single most common text-to-SQL failure is a **hallucinated column** or a **wrong category string**
(`status = 'ACTIVE'` when the warehouse stores `'Active'`). Storing schema in the brain guarantees drift.
Instead:

- `tools/show_schema.sh <table>` returns live column names/types.
- `tools/show_values.sh <table> <column>` returns the live distinct values *before* the agent filters on a
  categorical column.

Nothing schema-shaped is ever written into the brain, so nothing can go stale.

---

## 3. The gate ladder (rules as code, cheapest first)

`review.py` runs a finished query through an escalating ladder. **Order matters: the cheapest, most certain
checks run first, and any hard failure short-circuits before you spend a cent on the LLM.**

```
generated SQL
   │
 1 PII guard      tools/pii_guard.py   deterministic   ── ERROR → block, never runs
   │
 2 lint           tools/lint_sql.py    deterministic   ── ERROR → auto-revise, WARN → surface
   │
 3 dry-run        warehouse --dry_run  ~free           ── parse/columns/types valid? cost estimate
   │
 4 LLM review     the model             $$             ── the "salt": last, only if 1–3 passed
   │
 ▼
 accept  /  revise-and-retry (bounded loop)
```

Each linter finding **cites the brain section it enforces** — so a rule has exactly one home (the glossary),
and the gate is just the *mechanical check* of that rule. This is the concrete form of principle #2: a rule
you *can* mechanize lives as a check in `lint_sql.py`, not only as a sentence the model might overlook.

**Which rules become gates?** Any rule that is (a) high-confidence and (b) mechanically checkable. Examples
in this template's `lint_sql.py`:

- a mandatory scope filter is present (e.g. exclude test/fraud accounts),
- a fact table that must be bridged through the dimension actually joins it,
- counts use `COUNT(DISTINCT <entity>)`, not `COUNT(*)`,
- a subset flag filtered in `WHERE` under a `GROUP BY` (which silently drops zero-buckets),
- no PII column reaches the output,
- output columns follow the naming convention.

---

## 4. The trust loop (how the agent gets better — safely)

The agent is only trusted because it is **scored**, and improvement is a loop, not a one-off.

```
  edit the brain (glossary.md / semantic_model.yaml / sql_style.md)
        │
        ├─▶ fast gate    make check       structure + dry-run drift + linter self-test   (free)
        │
        ├─▶ component     make component   isolate ONE decision (routing/time/shape)      (fast, cheap)
        │                 └─ use this for small changes — no full end-to-end run needed
        │
        └─▶ full eval     make eval RUN=<id>
                          │  1 SNAPSHOT the brain + testset  → eval/runs/<id>/brain/      (version memory)
                          │  2 run every golden THROUGH the agent → generated SQL
                          │  3 execute + float-tolerant compare  → scorecard.json          (objective)
                          │  4 (optional) rubric critic on non-passes → critic.json        (subjective)
                          │  5 append to eval/runs/ledger.jsonl, tagged with the brain hash
                          ▼
                     read the diagnostics → find the SYSTEMATIC error → fix the ROOT → repeat
```

Four properties make this safe and honest:

1. **Sandboxed.** Eval runs against fixed golden cases in isolation; a scoring run can read the brain but
   cannot mutate the live workflow or the request history.
2. **Objective + subjective.** Known-answer SQL gives a hard pass/fail number; the rubric critic scores the
   things that have no single right answer (a deep dive's reasoning, a deck's clarity).
3. **Component before end-to-end.** A one-line glossary tweak doesn't need a full expensive run — a
   component eval isolates the single decision it should affect and gives fast signal. You pay for the full
   suite only when the change warrants it.
4. **Versioned + revertible.** Every run snapshots the brain and records a **brain hash** in the ledger. If a
   change makes the agent worse, `snapshot.py restore <id>` puts the last-good brain back, and the ledger +
   git history are a permanent record of every version and its score. *You cannot improve what you can't roll
   back.*

### Improve by pattern, not by patch

When the scorecard shows failures, the move is **not** to hand-fix each wrong answer. Read the diagnostics
across *all* failures, find the **one systematic cause** (a routing rule that's too loose, a metric defined
ambiguously, a missing gate), and fix it once at the root. One structural fix typically clears a whole class
of failures; fifty patches clear fifty and create the fifty-first.

---

## 5. Three run modes, one shape

The ask loop is the core. Two heavier modes reuse the exact same *live-brain + engine + gates* pattern — only
the method text differs:

| Mode | Module | Reads live | Output |
|---|---|---|---|
| **ask** | `agent/agent.py` | the ask loop rules in `prompt.py` | one answer + a saved artifact |
| **deep dive** | `agent/deep_dive.py` *(you add)* | your `deep_dive` method doc | a whole RCA folder (cohort analysis, RCA, survival analysis, …) |
| **deck** | `agent/create_deck.py` *(you add)* | your `create_deck` method doc | a slide deck, reviewed by a critic loop, then delivered |

The deep-dive and deck modules are **stubs to grow into** in this template — the README shows where they
plug in. They are what turn the agent from a Q&A box into something that does the **end-to-end job of a data
or product analyst**: scope a question, investigate it (cohorts, root-cause decomposition, survival curves),
reconcile every segment back to the headline number, and present the finding to stakeholders.

---

## 6. Safety guards (in code, not convention)

Autonomy needs guardrails that are *enforced*, not documented:

- **Per-run + per-session cost ceilings** (`config.py`): a single answer over `MAX_RUN_USD` warns; the
  session raises `BudgetExceeded` before starting the next question once it hits `MAX_SESSION_USD` — a
  backstop against a runaway loop (e.g. an unbounded eval).
- **Append-only cost log**: every run records model, status, cost, running total.
- **PII guard**: one module owns the PII policy; the linter delegates to it, so there is a single place to
  audit "what can never leave the warehouse."
- **Outward-action allowlist**: anything that leaves the system (email, Slack, a shared deck) checks a
  recipient/destination allowlist and supports a dry-run, so an autonomous run can't misfire to the wrong
  place.

These are the difference between a demo and something you can leave running.
