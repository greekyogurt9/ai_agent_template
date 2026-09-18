# ai_agent_template
I recently build an AI agent that accepts plain english questions and gives out answer by looking into datasets, building own queries and running them to get the answers. you can also do deep dives liek survival analysis statistical tests and create ppts to represent in front of stakeholders. I am here mentioning only template.

A **reference template for building a trustworthy text-to-SQL analytics agent on your own data.**

You describe what you want in plain English — *"how many active customers, split by segment?"* — and the
agent routes the question to the right table, applies your canonical business rules, verifies columns and
category values **live** against your warehouse, writes a runnable query, runs it, and returns an answer you
can trust. Push it further and the same engine runs full **root-cause deep dives** and builds
**stakeholder decks**.

This repo contains **no real business data or rules** — every table, column, and metric here is a generic
placeholder for a fictional company ("Acme"). It is a *scaffold + playbook*: copy it, point it at your
warehouse, and fill in your own brain.

> **Read `ARCHITECTURE.md` for the design, `GETTING_STARTED.md` for the step-by-step adaptation guide,
> and `ADAPT_TO_YOUR_DATA.md` to point it at your own datasets + glossary without breaking the gates (includes time estimates).**

---

## The one idea worth stealing

> **Treat the LLM like a sword, not a paring knife. You wouldn't use a sword to cut a lemon.**

Most text-to-SQL demos hand the model *everything* — routing, business rules, formatting, validation — and
hope. That works in a demo and fails the moment someone trusts the number. This template inverts it:

- Make as much of the pipeline **deterministic** as possible (routing metadata, linters, gates, comparators).
- Use the LLM only where genuine reasoning is required.
- The deterministic workflow is the recipe; **the LLM is the pinch of salt** at the end that checks the dish
  tastes right — not the whole kitchen.

Less LLM surface area = fewer places to be wrong = more trust.

---

## Six principles this template encodes

1. **Deterministic-first, LLM-as-salt.** Every step that *can* be code is code.
2. **A rule that can be a gate should never live only in a prompt.** Prose rules are hope; code gates are
   guarantees. Promote rules into linters, guards, and comparators wherever possible.
3. **Never store what you can look up.** Column names and category/enum values are fetched **live** from the
   warehouse at query time — nothing to keep in sync, no hallucinated columns.
4. **A single source of truth, read live.** The "brain" (routing + rules + style) lives in one place and is
   re-read on every run. The agent never keeps its own copy that can drift.
5. **If you can't measure it, you can't trust it.** A sandboxed, versioned evaluation harness scores every
   change — objectively (known-answer SQL) and subjectively (rubric-scored critic).
6. **Improve by hunting patterns, not one-off failures.** Fix the *systematic* error the eval surfaces once,
   at the root — not fifty individual wrong answers.

---

## The four layers

The agent is a thin orchestrator. Everything else is data it reads or a gate it must pass.

| # | Layer | Lives in | Role |
|---|---|---|---|
| 1 | **Brain** (read-only, live) | `brain/` + `tools/show_*` | routing + business rules + style + **live** schema/value introspection — the single source of truth |
| 2 | **Agent** (thin orchestrator) | `agent/` | builds the prompt from the live brain, drives the engine, enforces the gates |
| 3 | **Engines** (external) | your LLM CLI/SDK + your warehouse CLI | the model that reasons + the warehouse the SQL runs against |
| 4 | **Trust harness** | `eval/` | scores brain + agent before rollout; snapshots every version so a bad change is one revert away |

```
  you ─▶  ask "how many active customers by segment?"
              │
              ▼
   ┌──────────────  agent/ (thin orchestrator)  ──────────────┐
   │  1 build prompt   from the LIVE brain (brain/*, tools/*)  │
   │  2 budget check   refuse if session spend ≥ ceiling       │
   │  3 invoke engine  hand question to the LLM (headless)     │
   └───────────────────────────┬──────────────────────────────┘
                               │  (the loop the model runs itself)
                               ▼
      ROUTE       pick the right table from the semantic model
      INTROSPECT  tools/show_schema.sh / show_values.sh  (LIVE)
      APPLY RULES metric / active / fraud / grain  (from glossary)
      WRITE SQL   render per sql_style
      REVIEW      review.py: PII → lint → dry-run → LLM  (cheapest first)
      RUN         execute against the warehouse
      RETURN      answer + SQL + filters + caveat
                               │
                               ▼
        the answer  (+ a saved artifact you can re-read)
```

---

## Repo map

```
ai_agent_template/
  README.md              this file — what it is + the philosophy
  ARCHITECTURE.md        the design: 4 layers, the trust loop, the gate ladder
  GETTING_STARTED.md     adapt-to-your-data checklist (do this in order)
  Makefile               thin wrappers over the eval + checks

  brain/                 LAYER 1 — the single source of truth (edit these for YOUR data)
    semantic_model.yaml    routing / grain / keys / joins (structure only — no columns/values stored)
    glossary.md            canonical metric & identity MEANING (the non-obvious business rules)
    sql_style.md           how to render SQL canonically (counting / ratios / naming / determinism)

  tools/                 LAYER 1 — live introspection + deterministic GATES
    show_schema.sh         live column names/types for a table (engine-agnostic adapter)
    show_values.sh         live category/enum VALUES for a column (before you filter it)
    lint_sql.py            deterministic SQL linter — encodes rules as hard checks
    pii_guard.py           blocks queries that would surface PII (single source of PII policy)

  agent/                 LAYER 2 — the thin orchestrator (add-only; reads the brain live)
    config.py              model id, live-brain paths, cost budgets, warehouse/LLM auth surface
    prompt.py              assembles the system prompt from the LIVE brain (fails if a copy appears)
    agent.py               the ask loop: build → budget → invoke → parse → guard → save artifact
    review.py              pre-submit gate ladder: PII → lint → dry-run → LLM review → revise
    README.md              agent design notes

  eval/                  LAYER 4 — the trust harness (dev path, not the everyday path)
    golden_cases.yaml      SSOT — example question → known-answer SQL cases (tiered)
    run_eval.py            orchestrator — run goldens through the agent, score, record
    lib/comparator.py      float-tolerant, name-insensitive result comparator (objective eval)
    lib/component_eval.py  isolate ONE decision (routing / time-window / shape) — fast signal
    lib/snapshot.py        snapshot brain + testset each run; list / diff / revert
    lib/critic.py          rubric-scored LLM critic (subjective eval) skeleton
    runs/                  per-run bundles + append-only ledger (git-tracked version memory)
    README.md              how the trust loop works
```

---

## Quick start (after you adapt the brain)

```bash
# 0. one-time: point config at your warehouse + LLM, fill brain/ with your tables & rules
# 1. sanity — brain is read live, prompt assembles, gates self-test
make check

# 2. ask a question end to end (runs the SQL itself, saves an artifact)
python3 -m agent.agent "how many active customers do we have?"

# 3. score a change against the goldens, snapshotting this version of the brain
make eval RUN=my_first_run
```

See `GETTING_STARTED.md` for the full adaptation path.
