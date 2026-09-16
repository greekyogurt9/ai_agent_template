# agent/ — the thin orchestrator (Layer 2)

This is the only layer this template *owns* as a program. It reads the brain (Layer 1) live and is measured by
the eval harness (Layer 4). It is **add-only**: never copy a brain file in here (`prompt.verify_brain_is_live`
fails the build if you do — a forked brain is how a brain goes stale).

## Files

| file | role |
|---|---|
| `config.py` | one place for warehouse ids, model id, cost budgets, the outward-action allowlist |
| `prompt.py` | assembles the system prompt from the LIVE brain each run; `brain_hash()` is the version key |
| `agent.py` | the ask loop: build → budget → invoke → parse → guard → save artifact |
| `review.py` | the gate ladder: PII → lint → dry-run → LLM (cheapest first, short-circuits) |
| `runs/` | one `.md` artifact per answered question + `cost_log.tsv` |

## The loop

```
python3 -m agent.agent "how many active customers by segment?"
   │
   ├─ prompt.build_agent_system_prompt()   reads brain/*.{yaml,md} LIVE
   ├─ Analyst.ask()                        budget check → _invoke() → parse → log → artifact
   │     └─ the headless LLM runs: ROUTE → INTROSPECT (show_schema/show_values) → RULES → SQL → REVIEW → RUN
   └─ writes runs/<slug>_<date>.md         re-readable answer envelope
```

## Swapping the LLM engine

Only `agent._invoke()` cares whether the engine is a CLI (keyless — uses its own login) or an SDK (needs a
key). Keep the return shape `{text, cost_usd, duration_ms}` and nothing else changes. Start keyless; move to an
SDK when you go multi-channel (Slack/web).

## Guards (enforced here, not by convention)

- **Per-run warn / session ceiling** — `Analyst` tracks `spent_usd` and raises `BudgetExceeded` before the
  next question once the ceiling is hit; a single expensive run warns. Backstops a runaway loop.
- **Cost log** — every run appends to `runs/cost_log.tsv`.
- **Outward allowlist** — `config.OUTWARD_ALLOWLIST` gates anything that leaves the system.

## Heavier modes to grow into (stubs)

The ask loop is the core. Two analyst-grade modes reuse the *same* live-brain + engine + gates pattern; add
them as siblings when the ask loop is solid:

- **`deep_dive.py`** — reads a `deep_dive` method doc live and runs a full root-cause investigation: cohort
  analysis, metric decomposition, survival analysis, segment reconciliation to the headline delta. Output is a
  folder (charts + data + a findings README), not a single answer.
- **`create_deck.py`** — reads a `create_deck` method doc live, builds a stakeholder deck from a deep-dive
  folder, scores it with a rubric **critic** (subjective eval) in a loop until it clears a bar, then delivers
  it through an **allowlisted** channel (dry-run supported so an autonomous run can't misfire).

Together these are what make the agent do the **end-to-end job of a data / product analyst** — not just answer
questions, but investigate and present.
