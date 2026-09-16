# eval/ — the trust harness (Layer 4)

The agent is only trusted because it is **scored**. This is the dev-time path, not the everyday one — but it
is what gates rollout and lets you improve safely.

## The three gates, cheap → expensive

| gate | command | cost | when |
|---|---|---|---|
| **check** | `make check` | free | after any edit — brain-live + linter/PII/comparator self-tests |
| **component** | `make component` | cheap | after a small brain edit — isolate ONE decision (routing/time/shape) |
| **full** | `make eval RUN=<id>` | $$ | when a change warrants it — goldens through the agent, executed + scored |

**Component before end-to-end.** A one-line glossary tweak doesn't need a full expensive run. The component
eval asks the model just the single decision the edit should affect and checks it deterministically.

## Objective + subjective

- **Objective** (`lib/comparator.py`) — the agent's SQL result vs the golden result, compared with a
  **float-tolerant, name-insensitive, order-insensitive** comparator. This matters: warehouse float sums
  aren't bit-reproducible, so a naive diff gives false failures. Run `python3 -m eval.lib.comparator --selftest`.
- **Subjective** (`lib/critic.py`) — a rubric-scored LLM critic for outputs with no single right answer (a
  deep dive's reasoning, a deck's clarity). Explicit rubric + hard pass bar + a caps rule for fatal flaws.

## Sandboxed + versioned + revertible

- **Sandboxed** — the eval runs fixed golden cases in isolation; it reads the brain but never mutates the live
  workflow.
- **Versioned** — every full run **snapshots the brain** into `runs/<id>/brain/` and appends a record to
  `runs/ledger.jsonl` tagged with the **brain hash** (same hash = same brain; changed hash = a real edit whose
  score delta you can attribute).
- **Revertible** — if a change made things worse: `python3 -m eval.lib.snapshot restore <id>` puts the
  last-good brain back. Commit the runs you like — git + the ledger are permanent version memory.

## The improvement loop (pattern, not patch)

```
edit brain → make check → make component → make eval RUN=<id>
     ▲                                            │
     └──── fix the ROOT of the systematic error ──┘
```

When the scorecard shows failures, do **not** hand-fix each wrong answer. Read across all failures, find the
**one systematic cause** (a loose routing rule, an ambiguous metric, a missing gate), fix it once at the root,
and re-run. One structural fix clears a whole class of failures.

## Files

| file | role |
|---|---|
| `golden_cases.yaml` | SSOT — question → known-answer SQL, tiered (core/extended) |
| `run_eval.py` | orchestrator — `check` / `component` / `run` subcommands |
| `lib/comparator.py` | float-tolerant objective comparator (+ self-test) |
| `lib/component_eval.py` | isolate one decision (routing example included) |
| `lib/critic.py` | rubric-scored subjective critic (skeleton) |
| `lib/snapshot.py` | snapshot / list / diff / restore the brain |
| `runs/` | per-run scorecards + `ledger.jsonl` (git-tracked version memory) |
