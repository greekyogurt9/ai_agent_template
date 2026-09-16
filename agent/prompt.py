"""prompt.py — assemble the system prompt from the LIVE brain, every run.

The whole point: the agent has NO baked-in knowledge. It reads brain/semantic_model.yaml, brain/glossary.md,
and brain/sql_style.md from disk each time, and appends the fixed LOOP RULES that tell the model how to run
the route → introspect → rules → dates → SQL → review loop.

`verify_brain_is_live()` FAILS if a copy of any brain file ever appears inside agent/ — a forked copy is how a
brain goes stale, so the template makes it impossible by construction.

    python3 -m agent.prompt     # assert brain is live, print the prompt size + hash
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from agent import config


# --- the FIXED loop rules (method text; the only agent-owned instructions) ---
LOOP_RULES = """
You are an analytics agent. Answer the user's data question by running this loop yourself, using your
shell/tools. Do NOT guess anything you can look up.

1. ROUTE      — pick exactly ONE table from the semantic model above. State which and why.
2. INTROSPECT — get live columns with `tools/show_schema.sh <table>`. Before filtering ANY categorical
                column, get its real values with `tools/show_values.sh <table> <column>`. Never invent a
                column name or a category string.
3. APPLY RULES— apply the glossary rules for the metric, the entity, and the MANDATORY SCOPE filters. Do
                not add a filter the question did not ask for (over-filtering is the most common error).
4. DATES      — if a date window is implied but not exact, STOP and ask for the range. If you assume one,
                state it in the answer.
5. WRITE SQL  — render per sql_style (COUNT DISTINCT the entity; named snake_case output; safe division;
                deterministic ordering).
6. REVIEW     — the SQL must pass the review gate (PII → lint → dry-run → LLM). Fix any ERROR and retry.
7. RUN        — execute against the warehouse.
8. RETURN     — a fixed envelope:
                  STATUS: OK | NEEDS_CLARIFICATION
                  ANSWER: <plain-English answer with the number>
                  TABLE_USED: <table>
                  SQL: <the exact query you ran>
                  FILTERS: <the scope/filters applied>
                  CAVEAT: <the one caveat the reader must know, or "none">
""".strip()


def verify_brain_is_live() -> None:
    """Fail loudly if any brain file has been copied into agent/ (would fork the source of truth)."""
    for src in config.BRAIN_FILES:
        clone = config.AGENT_DIR / src.name
        if clone.exists():
            raise RuntimeError(
                f"Brain file copied into agent/: {clone}. The agent must read the brain LIVE from "
                f"{config.BRAIN_DIR}/ — delete the copy. (A forked brain goes stale.)")
    for src in config.BRAIN_FILES + (config.SHOW_SCHEMA, config.SHOW_VALUES):
        if not src.exists():
            raise FileNotFoundError(f"Missing brain file: {src}")


def brain_hash() -> str:
    """12-char hash of the brain — the version key. Same hash = same brain; changed hash = a real edit."""
    h = hashlib.sha256()
    for src in config.BRAIN_FILES:
        h.update(src.read_bytes())
    return h.hexdigest()[:12]


def build_agent_system_prompt() -> str:
    """The full system prompt: live brain + fixed loop rules. Read fresh from disk every call."""
    verify_brain_is_live()
    parts = [
        "# SEMANTIC MODEL (routing / grain / keys / joins)",
        config.SEMANTIC_MODEL.read_text(),
        "\n# BUSINESS GLOSSARY (canonical rules — the single rulebook)",
        config.GLOSSARY.read_text(),
        "\n# SQL STYLE (how to render the query)",
        config.SQL_STYLE.read_text(),
        "\n# LOOP RULES",
        LOOP_RULES,
        f"\n# WAREHOUSE: {config.WAREHOUSE_ENGINE} {config.WAREHOUSE_PROJECT}.{config.WAREHOUSE_DATASET}",
    ]
    return "\n\n".join(parts)


if __name__ == "__main__":
    verify_brain_is_live()
    p = build_agent_system_prompt()
    print(f"brain is live: OK")
    print(f"brain hash:    {brain_hash()}")
    print(f"prompt size:   {len(p):,} chars")
