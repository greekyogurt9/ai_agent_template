#!/usr/bin/env bash
# ============================================================================
# show_schema.sh  (Layer 1 — live introspection)
# ----------------------------------------------------------------------------
# Print the LIVE column names + types for one table, straight from the warehouse.
# The agent calls this at query time so it never guesses or remembers a column.
# NOTHING schema-shaped is ever stored in the brain — this is how we avoid drift.
#
# Usage:   tools/show_schema.sh <table_name>
# Example: tools/show_schema.sh fct_orders_daily
#
# Adapt the query below to YOUR warehouse (one block is active; others are
# reference). Keep the OUTPUT shape stable: two columns, `name` and `type`.
# ============================================================================
set -euo pipefail

TABLE="${1:?usage: show_schema.sh <table_name>}"

# --- config (mirror agent/config.py) ---------------------------------------
PROJECT="${WAREHOUSE_PROJECT:-your-project}"
DATASET="${WAREHOUSE_DATASET:-acme_analytics}"

# --- BigQuery (active example) ---------------------------------------------
# INFORMATION_SCHEMA scans are essentially free (tiny bytes).
bq query --use_legacy_sql=false --format=csv --quiet \
  "SELECT column_name AS name, data_type AS type
   FROM \`${PROJECT}.${DATASET}\`.INFORMATION_SCHEMA.COLUMNS
   WHERE table_name = '${TABLE}'
   ORDER BY ordinal_position"

# --- Snowflake (reference — swap in if you use Snowflake) -------------------
# snowsql -o friendly=false -o header=true -o output_format=csv -q \
#   "SELECT column_name AS name, data_type AS type
#    FROM ${DATASET}.INFORMATION_SCHEMA.COLUMNS
#    WHERE table_name = UPPER('${TABLE}')
#    ORDER BY ordinal_position;"

# --- Postgres (reference) --------------------------------------------------
# psql "$PGCONN" -F',' --no-align -c \
#   "SELECT column_name AS name, data_type AS type
#      FROM information_schema.columns
#     WHERE table_name = '${TABLE}'
#     ORDER BY ordinal_position;"
