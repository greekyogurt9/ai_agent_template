"""run_eval.py — the eval orchestrator. One subcommand per action.

    python3 -m eval.run_eval check                 free: brain live + linter/comparator self-tests
    python3 -m eval.run_eval component [name]       fast: isolate ONE decision (default: route)
    python3 -m eval.run_eval run <run_id> [tier]    full: snapshot brain, run goldens through the agent,
                                                     execute + compare, score, record to the ledger

The FULL run is the expensive one — it needs the LLM engine + warehouse wired (config.py). `check` and
`component` are free/cheap and are what you run after most small edits. This mirrors the trust loop in
ARCHITECTURE.md: component before end-to-end; snapshot every full run so a bad change is one revert away.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

from agent import config, prompt
from eval.lib import comparator, component_eval, snapshot

ROOT = Path(__file__).resolve().parent
GOLDENS = ROOT / "golden_cases.yaml"
RUNS = ROOT / "runs"
LEDGER = RUNS / "ledger.jsonl"


# --- free integrity gate ----------------------------------------------------
def cmd_check() -> int:
    prompt.verify_brain_is_live()
    print("brain is live: OK   hash:", prompt.brain_hash())
    tools = ROOT.parent / "tools"
    rc = 0
    for name, mod in (("lint_sql", tools / "lint_sql.py"),
                      ("pii_guard", tools / "pii_guard.py")):
        r = subprocess.run([sys.executable, str(mod), "--selftest"], capture_output=True, text=True)
        ok = r.returncode == 0
        rc |= (0 if ok else 1)
        print(f"gate {name} self-test: {'PASS' if ok else 'FAIL'}")
    r = comparator._selftest()
    rc |= r
    return rc


# --- cheap component gate ---------------------------------------------------
def cmd_component(name: str = "route") -> int:
    return component_eval.main([name])


# --- expensive full run -----------------------------------------------------
def _execute(sql: str) -> list:
    """Run SQL and return rows (list of lists), header stripped. EDIT for your warehouse.
    Engine-aware: dispatches on agent/config.py WAREHOUSE_ENGINE (bigquery |
    snowflake | postgres). Returns [] and prints a note in template mode (no
    warehouse CLI)."""
    sql = sql.replace("${PROJECT}", config.WAREHOUSE_PROJECT).replace("${DATASET}", config.WAREHOUSE_DATASET)
    engine = str(getattr(config, "WAREHOUSE_ENGINE", "bigquery")).lower()
    try:
        if engine == "snowflake":
            r = subprocess.run(
                ["snowsql", "-o", "friendly=false", "-o", "header=true",
                 "-o", "output_format=csv", "-q", sql],
                capture_output=True, text=True, timeout=300)
        elif engine == "postgres":
            import os as _os
            pgconn = _os.environ.get("PGCONN", "")
            r = subprocess.run(
                ["psql", pgconn, "-F,", "--no-align", "-c", sql],
                capture_output=True, text=True, timeout=300)
        else:  # bigquery (default)
            r = subprocess.run(["bq", "query", "--use_legacy_sql=false", "--format=csv", "--quiet", sql],
                               capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        print("  [template mode] warehouse CLI not found — cannot execute", file=sys.stderr)
        return []
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return [ln.split(",") for ln in lines[1:]]     # strip header row


def cmd_run(run_id: str, tier: str | None = None) -> int:
    cases = yaml.safe_load(GOLDENS.read_text())["cases"]
    if tier:
        cases = [c for c in cases if c.get("tier") == tier]

    # 1) SNAPSHOT the brain for this run (version memory / revert point)
    snapshot.save(run_id)

    from agent.agent import Analyst
    analyst = Analyst()
    scorecard = []
    for c in cases:
        row = {"id": c["id"], "question": c["question"]}
        try:
            # 2) run the question THROUGH the real agent (its SQL, its loop)
            ans = analyst.ask(c["question"])
            row["cost_usd"] = ans.cost_usd
            agent_sql = _extract_sql(ans.text)
            # 3) execute both, compare results
            got = _execute(agent_sql) if agent_sql else []
            exp = _execute(c["reference_sql"])
            cr = comparator.compare(exp, got)
            row.update(passed=cr.passed, reason=cr.reason)
        except Exception as e:                       # noqa: BLE001 — record, don't crash the run
            row.update(passed=False, reason=f"error: {e}")
        status = "PASS" if row.get("passed") else "FAIL"
        print(f"  [{status}] {c['id']}: {row.get('reason','')}")
        scorecard.append(row)

    n = len(scorecard)
    passed = sum(1 for r in scorecard if r.get("passed"))
    rate = passed / n if n else 0.0

    # 4) persist scorecard + append to the ledger, tagged with the brain hash
    out = RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "scorecard.json").write_text(json.dumps(scorecard, indent=2))
    _append_ledger(run_id, rate, passed, n)
    print(f"\nRUN {run_id}: {passed}/{n} = {rate:.0%}   brain {prompt.brain_hash()}")
    print(f"  scorecard: {out/'scorecard.json'}   ledger: {LEDGER}")
    print("  → read the failures, find the SYSTEMATIC cause, fix the ROOT in brain/, re-run.")
    return 0


def _extract_sql(text: str) -> str:
    import re
    m = re.search(r"SQL:\s*(.+?)(?:\nFILTERS:|\nCAVEAT:|\Z)", text, re.DOTALL)
    return m.group(1).strip().strip("`") if m else ""


def _append_ledger(run_id: str, rate: float, passed: int, n: int) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": run_id, "date": str(date.today()), "brain_hash": prompt.brain_hash(),
           "pass_rate": round(rate, 4), "passed": passed, "total": n, "model": config.MODEL}
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "check":
        return cmd_check()
    if cmd == "component":
        return cmd_component(rest[0] if rest else "route")
    if cmd == "run":
        if not rest:
            print("usage: run <run_id> [tier]")
            return 2
        return cmd_run(rest[0], rest[1] if len(rest) > 1 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
