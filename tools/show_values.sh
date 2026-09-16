#!/usr/bin/env bash
# ============================================================================
# show_values.sh  (Layer 1 — live introspection)
# ----------------------------------------------------------------------------
# Print the LIVE distinct values of a categorical column (with row counts), so
# the agent filters on the REAL string ('Active' vs 'ACTIVE' vs 'active') instead
# of guessing. Call this before writing any WHERE on a categorical column.
#
# Usage:   tools/show_values.sh <table_name> <column_name> [limit]
# Example: tools/show_values.sh fct_orders_daily channel
#
# Adapt to YOUR warehouse. Keep OUTPUT stable: `value`, `n` (row count), desc.
# ============================================================================
set -euo pipefail

TABLE="${1:?usage: show_values.sh <table> <column> [limit]}"
COLUMN="${2:?usage: show_values.sh <table> <column> [limit]}"
LIMIT="${3:-50}"

PROJECT="${WAREHOUSE_PROJECT:-your-project}"
DATASET="${WAREHOUSE_DATASET:-acme_analytics}"

# --- BigQuery (active example) ---------------------------------------------
# NOTE: this scans the column; keep the limit modest. For very large tables,
# prefer a sampled or partition-restricted variant.
bq query --use_legacy_sql=false --format=csv --quiet \
  "SELECT CAST(${COLUMN} AS STRING) AS value, COUNT(*) AS n
   FROM \`${PROJECT}.${DATASET}.${TABLE}\`
   GROUP BY value
   ORDER BY n DESC
   LIMIT ${LIMIT}"

# --- Snowflake (reference) -------------------------------------------------
# snowsql -o friendly=false -o header=true -o output_format=csv -q \
#   "SELECT ${COLUMN}::string AS value, COUNT(*) AS n
#    FROM ${DATASET}.${TABLE}
#    GROUP BY value ORDER BY n DESC LIMIT ${LIMIT};"

# --- Postgres (reference) --------------------------------------------------
# psql "$PGCONN" -F',' --no-align -c \
#   "SELECT ${COLUMN}::text AS value, COUNT(*) AS n
#      FROM ${TABLE} GROUP BY value ORDER BY n DESC LIMIT ${LIMIT};"
