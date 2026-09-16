"""review.py — the pre-submit GATE LADDER (rules as code, cheapest first).

A finished query runs this ladder before its answer is accepted. Order is the whole point: the cheapest,
most-certain checks run first and a hard failure short-circuits BEFORE spending a cent on the LLM.

    1 PII guard    deterministic   ERROR → block (never runs)
    2 lint         deterministic   ERROR → must fix;  WARN → surface
    3 dry-run      ~free           parse/columns/types valid? cost estimate
    4 LLM review   $$              the "salt": last, only if 1–3 passed

The LLM step is deliberately LAST and OPTIONAL — most bad queries are caught for free by steps 1–3.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# import the deterministic gates by path (tools/ is not a package)
import importlib.util
import sys

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(TOOLS / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


lint_sql = _load("lint_sql")


@dataclass
class ReviewResult:
    ok: bool
    stage: str                      # the stage that decided the outcome
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    dry_run_bytes: int | None = None
    notes: str = ""


def _dry_run(sql: str) -> tuple[bool, str, int | None]:
    """Validate the SQL WITHOUT executing it. Returns (ok, message, estimated_bytes).
    EDIT for your warehouse. BigQuery example shown; Snowflake→EXPLAIN, Postgres→EXPLAIN."""
    try:
        proc = subprocess.run(
            ["bq", "query", "--use_legacy_sql=false", "--dry_run", "--format=none", sql],
            capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return False, proc.stderr.strip()[:400], None
        # bq prints the byte estimate to stderr; parse if you want a cost gate here
        return True, "dry-run ok", None
    except FileNotFoundError:
        return True, "dry-run skipped (warehouse CLI not found — template mode)", None
    except subprocess.TimeoutExpired:
        return False, "dry-run timed out", None


def review(sql: str, out_columns=None, llm_review=None) -> ReviewResult:
    """Run the gate ladder. `llm_review` is an optional callable(sql)->(ok, notes) for the final salt step."""
    findings = lint_sql.lint_sql(sql, out_columns)
    errors = [f for f in findings if f.level == "ERROR"]
    warnings = [f for f in findings if f.level == "WARN"]

    # stage 1+2: deterministic gates (PII findings surface here too, as ERRORs)
    if errors:
        return ReviewResult(ok=False, stage="lint/pii", errors=errors, warnings=warnings)

    # stage 3: dry-run
    ok, msg, nbytes = _dry_run(sql)
    if not ok:
        return ReviewResult(ok=False, stage="dry_run", errors=[msg], warnings=warnings)

    # stage 4: LLM review — the salt. Only reached if everything above passed.
    if llm_review is not None:
        lok, notes = llm_review(sql)
        if not lok:
            return ReviewResult(ok=False, stage="llm", errors=[notes], warnings=warnings,
                                dry_run_bytes=nbytes)
        return ReviewResult(ok=True, stage="llm", warnings=warnings, dry_run_bytes=nbytes, notes=notes)

    return ReviewResult(ok=True, stage="dry_run", warnings=warnings, dry_run_bytes=nbytes, notes=msg)


if __name__ == "__main__":
    import sys as _sys
    r = review(_sys.stdin.read())
    print(f"ok={r.ok} stage={r.stage}")
    for e in r.errors:
        print("  ERROR:", e)
    for w in r.warnings:
        print("  WARN :", w)
