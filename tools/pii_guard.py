#!/usr/bin/env python3
"""PII guard — the SINGLE source of truth for "what can never leave the warehouse."

The linter (tools/lint_sql.py) and the review gate (agent/review.py) both delegate here, so there is
exactly ONE place to audit the PII policy. Keeping it separate from the linter means a security reviewer
can read this one file and know the whole policy.

Two checks:
  1. a PII column named in the SELECT projection (static — works before the query runs)
  2. a PII-looking column in the EXECUTED result headers (dynamic — catches SELECT * surprises)

EDIT the blocklist below for your schema. Prefer a small, explicit list of real PII columns plus a few
conservative name patterns. Over-broad patterns cause false positives and train people to ignore the guard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# --- policy: EDIT for your warehouse ---------------------------------------
# Exact column names that are PII and must never appear in output.
PII_COLUMNS = {
    "email", "contact_email", "phone", "phone_number", "full_name", "first_name",
    "last_name", "street_address", "address_line1", "tax_id", "national_id",
    "date_of_birth", "ip_address", "card_number", "bank_account",
}

# Conservative name patterns (substring, case-insensitive) — keep tight.
PII_PATTERNS = (
    r"e?mail", r"phone", r"ssn", r"passport", r"national_id", r"tax_id",
    r"dob|date_of_birth", r"street|address_line", r"card_num", r"iban|bank_account",
)

# Identifiers that LOOK like the patterns but are safe to output (allow-list wins over patterns).
PII_ALLOW = {"customer_id", "signup_id", "order_id", "address_country", "email_domain_bucket"}


@dataclass
class PiiFinding:
    message: str


def _looks_pii(name: str) -> bool:
    n = (name or "").strip().strip("`\"").lower()
    if not n or n in PII_ALLOW:
        return False
    if n in PII_COLUMNS:
        return True
    return any(re.search(p, n) for p in PII_PATTERNS)


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def scan_sql(sql: str, out_columns=None):
    """Return PiiFinding list. `out_columns` = executed result headers (any case), if available."""
    findings = []
    s = _strip_comments(sql or "").lower()

    # (1) static: a known PII column referenced anywhere in the SQL text
    for col in sorted(PII_COLUMNS):
        if col in PII_ALLOW:
            continue
        if re.search(rf"(?<![.\w]){re.escape(col)}\b", s):
            findings.append(PiiFinding(f"PII column `{col}` referenced in the query"))

    # (2) dynamic: a PII-looking column in the actual output headers
    for col in (out_columns or []):
        if _looks_pii(col):
            findings.append(PiiFinding(f"output column `{col}` looks like PII"))

    # de-dup by message, preserve order
    seen, uniq = set(), []
    for fnd in findings:
        if fnd.message not in seen:
            seen.add(fnd.message)
            uniq.append(fnd)
    return uniq


def _selftest() -> int:
    ok = True
    checks = [
        ("SELECT customer_id, email FROM t", None, True),
        ("SELECT customer_id, COUNT(*) FROM t", None, False),
        ("SELECT customer_id FROM t", ["customer_id", "phone_number"], True),
        ("SELECT customer_id, email_domain_bucket FROM t", None, False),  # allow-listed
    ]
    for i, (sql, cols, expect_hit) in enumerate(checks):
        hit = len(scan_sql(sql, cols)) > 0
        status = "PASS" if hit == expect_hit else "FAIL"
        ok = ok and hit == expect_hit
        print(f"  pii case {i}: {status}  hit={hit} expect={expect_hit}")
    print("PII SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    for fnd in scan_sql(sys.stdin.read()):
        print(fnd.message)
