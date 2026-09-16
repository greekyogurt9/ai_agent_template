"""config.py — the single place for paths, model id, budgets, and the auth surface.

EDIT the values marked `<-- EDIT` for your setup. Everything else in the agent reads from here, so there is
one place to change the warehouse, the model, or the cost ceilings.

    python3 -m agent.config     # print the resolved config + a sanity check
"""
from __future__ import annotations

import os
from pathlib import Path

# --- paths: the LIVE brain (never copied into agent/) -----------------------
AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent
BRAIN_DIR = ROOT / "brain"
TOOLS_DIR = ROOT / "tools"

SEMANTIC_MODEL = BRAIN_DIR / "semantic_model.yaml"
GLOSSARY = BRAIN_DIR / "glossary.md"
SQL_STYLE = BRAIN_DIR / "sql_style.md"
SHOW_SCHEMA = TOOLS_DIR / "show_schema.sh"
SHOW_VALUES = TOOLS_DIR / "show_values.sh"

# The files that make up the versioned "brain" (used for the brain-hash + snapshots).
BRAIN_FILES = (SEMANTIC_MODEL, GLOSSARY, SQL_STYLE)

# --- warehouse (Layer 3) ----------------------------------------------------
WAREHOUSE_ENGINE = os.environ.get("WAREHOUSE_ENGINE", "bigquery")     # <-- EDIT: bigquery|snowflake|postgres
WAREHOUSE_PROJECT = os.environ.get("WAREHOUSE_PROJECT", "your-project")  # <-- EDIT
WAREHOUSE_DATASET = os.environ.get("WAREHOUSE_DATASET", "acme_analytics")  # <-- EDIT

# --- LLM engine (Layer 3) ---------------------------------------------------
# The template drives an LLM headlessly. Two common shapes:
#   (a) an agent CLI in print mode (keyless — uses its own login), OR
#   (b) an SDK client (needs an API key).
# Only agent.py's _invoke() changes when you swap these.
MODEL = os.environ.get("AGENT_MODEL", "your-model-id")               # <-- EDIT
LLM_CLI = os.environ.get("AGENT_LLM_CLI", "llm")                     # <-- EDIT: your headless LLM command

# --- cost & safety guards (enforced in code — see agent.py) ------------------
MAX_RUN_USD = float(os.environ.get("MAX_RUN_USD", "3.0"))            # warn above this per single answer
MAX_SESSION_USD = float(os.environ.get("MAX_SESSION_USD", "50.0"))   # hard stop for the session
COST_LOG = AGENT_DIR / "runs" / "cost_log.tsv"

# --- outward-action allowlist (email/Slack/etc.) ----------------------------
# Anything that leaves the system checks this. Keep it tight.
OUTWARD_ALLOWLIST = tuple(
    x for x in os.environ.get("OUTWARD_ALLOWLIST", "you@example.com").split(",") if x
)


def summary() -> str:
    lines = [
        "Analytics Agent — resolved config",
        f"  root            {ROOT}",
        f"  brain files     {', '.join(p.name for p in BRAIN_FILES)}",
        f"  warehouse       {WAREHOUSE_ENGINE}  {WAREHOUSE_PROJECT}.{WAREHOUSE_DATASET}",
        f"  model           {MODEL}   (via `{LLM_CLI}`)",
        f"  budgets         run<=${MAX_RUN_USD}  session<=${MAX_SESSION_USD}",
        f"  outward allow   {', '.join(OUTWARD_ALLOWLIST) or '(none)'}",
    ]
    # sanity: brain files present?
    missing = [p.name for p in BRAIN_FILES + (SHOW_SCHEMA, SHOW_VALUES) if not p.exists()]
    lines.append(f"  brain present   {'OK' if not missing else 'MISSING: ' + ', '.join(missing)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
