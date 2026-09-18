#!/usr/bin/env python3
"""Deterministic pre-submit SQL linter (NO LLM) — the core "rules as gates" mechanism.

This encodes, as mechanical checks, the high-confidence rules that live in brain/glossary.md and
brain/sql_style.md. Each finding CITES the brain section it enforces, so a rule has exactly one home
(the brain) and this file is just its enforcement. Run it on generated SQL before an answer is accepted.

The checks below target the fictional "Acme" schema (see brain/semantic_model.yaml). ADAPT them to your
columns — the *shapes* of the checks are the reusable part, not the specific column names.

Usage:
    from tools.lint_sql import lint_sql
    findings = lint_sql(sql, out_columns=[...])   # out_columns optional (executed result headers)

    python3 tools/lint_sql.py < query.sql          # prints findings; exit 1 if any ERROR
    python3 tools/lint_sql.py --selftest           # verify the checks fire on the right cases
"""
from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema signatures — EDIT THESE by editing brain/semantic_model.yaml `policy:`
# (NOT here). The loader below reads the policy block automatically, so a
# dataset swap = one YAML edit, and the linter follows. The constants below are
# FALLBACK defaults (the Acme example) used only when the policy block or the
# YAML library is unavailable — keep them in sync with semantic_model.yaml.
# ---------------------------------------------------------------------------
_DEFAULT_DIM = "dim_customer_latest"
_DEFAULT_FACTS = ("fct_orders_daily", "fct_product_usage_monthly")
_DEFAULT_ENTITY_KEY = "customer_id"
_DEFAULT_SCOPE_COLUMNS = ("is_test", "is_fraud")
_DEFAULT_SUBSET_FLAGS = ("is_active_month",)
_DEFAULT_MONEY_COLUMNS = ("order_amount",)


def _load_policy():
    """Read the `policy:` block from brain/semantic_model.yaml. Returns a dict
    of overrides (possibly empty). Never raises — falls back to defaults."""
    try:
        from pathlib import Path as _Path
        candidates = [
            _Path(__file__).resolve().parent.parent / "brain" / "semantic_model.yaml",
            _Path.cwd() / "brain" / "semantic_model.yaml",
        ]
        model_path = next((p for p in candidates if p.exists()), None)
        if model_path is None:
            return {}
        text = model_path.read_text()
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text) or {}
        except ImportError:
            # Minimal fallback: parse the small `policy:` block without PyYAML.
            import re as _re
            m = _re.search(r"^policy:\s*\n((?:[ ]+.+\n?)+)", text, _re.MULTILINE)
            if not m:
                return {}
            data = {"policy": {}}
            cur_key, vals = None, []
            for line in m.group(1).splitlines():
                kv = _re.match(r"\s{2}(\w+):\s*(.*)", line)
                item = _re.match(r"\s*-\s*(.+)", line)
                if kv:
                    if cur_key:
                        data["policy"][cur_key] = vals if vals else {}
                    cur_key, vals = kv.group(1), []
                    rest = kv.group(2).strip()
                    if rest:
                        data["policy"][cur_key] = rest
                elif item and cur_key:
                    vals.append(item.group(1).strip())
            if cur_key and vals:
                data["policy"][cur_key] = vals
        policy = (data or {}).get("policy") or {}
        if not isinstance(policy, dict):
            return {}
        return policy
    except Exception:
        return {}


_POLICY = _load_policy()


def _policy_list(key, default):
    vals = _POLICY.get(key, default)
    if isinstance(vals, str):
        return (vals,)
    try:
        return tuple(v for v in vals if v)
    except TypeError:
        return default


DIM = str(_POLICY.get("dim_table", _DEFAULT_DIM))
FACT_TABLES = _policy_list("fact_tables", _DEFAULT_FACTS)
ENTITY_KEY = str(_POLICY.get("entity_key", _DEFAULT_ENTITY_KEY))
SCOPE_COLUMNS = _policy_list("scope_columns", _DEFAULT_SCOPE_COLUMNS)

# current-per-period subset flags that, filtered in a WHERE under a dimension GROUP BY, drop zero-buckets
SUBSET_FLAGS = _policy_list("subset_flags", _DEFAULT_SUBSET_FLAGS)

# money measure columns whose SUM(...) must be aliased *_revenue (sql_style §D)
MONEY_COLUMNS = _policy_list("money_columns", _DEFAULT_MONEY_COLUMNS)

# Backward-compatible aliases: the mandatory scope columns that must appear on
# any query touching the dimension (glossary: Mandatory scope). Prefer
# SCOPE_COLUMNS for new code; these cover the common two-column case.
SCOPE_TEST = SCOPE_COLUMNS[0] if len(SCOPE_COLUMNS) > 0 else _DEFAULT_SCOPE_COLUMNS[0]
SCOPE_FRAUD = SCOPE_COLUMNS[1] if len(SCOPE_COLUMNS) > 1 else _DEFAULT_SCOPE_COLUMNS[1]


# ---------------------------------------------------------------------------
@dataclass
class Finding:
    level: str      # "ERROR" (block) | "WARN" (surface)
    code: str
    message: str
    rule: str       # the brain section it enforces

    def __str__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}  ({self.rule})"


def _load_pii_guard():
    """Load tools/pii_guard.py robustly whether imported as a package or by path."""
    if "pii_guard" in sys.modules:
        return sys.modules["pii_guard"]
    try:
        import pii_guard  # type: ignore
        return pii_guard
    except ImportError:
        spec = importlib.util.spec_from_file_location(
            "pii_guard", str(Path(__file__).resolve().parent / "pii_guard.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


# --- depth-aware WHERE parsing (so a flag inside a SELECT-list IF() is NOT mistaken for a filter) -----
_WHERE_TERMINATORS = ("group by", "having", "order by", "qualify", "window",
                      "union", "except", "intersect")


def _where_clauses(low: str):
    """(start_offset, predicate_text) per WHERE, each running to its clause terminator or closing paren."""
    spans, n = [], len(low)
    for m in re.finditer(r"\bwhere\b", low):
        start = m.end()
        depth, j = 0, start
        while j < n:
            ch = low[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and any(low.startswith(t, j) for t in _WHERE_TERMINATORS):
                break
            j += 1
        spans.append((start, low[start:j]))
    return spans


def _last_group_by_is_time_only(low: str) -> bool:
    """True when the outermost GROUP BY keys are ALL time/period columns — the sanctioned
    'active within the period' cohort pattern, which is NOT a zero-bucket-dropping dimension group."""
    gbs = list(re.finditer(r"\bgroup by\b", low))
    if not gbs:
        return False
    rest = low[gbs[-1].end():]
    stop = re.search(r"\border by\b|\bhaving\b|\bqualify\b|\bwindow\b|\)", rest)
    gb = rest[:stop.start()] if stop else rest
    keys = [k.strip() for k in gb.split(",") if k.strip()]

    def _is_time(k: str) -> bool:
        return bool(re.search(r"date_trunc|extract\s*\(\s*(year|month|week|day|quarter)"
                              r"|_month\b|_year\b|\bmonth\b|\byear\b", k))
    return bool(keys) and all(_is_time(k) for k in keys)


# --- output-column naming (sql_style §D) -----------------------------------
def _split_top_commas(text: str):
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1; cur.append(ch)
        elif ch == ")":
            depth -= 1; cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _final_select_items(sql: str):
    """(expr, alias) for the OUTERMOST SELECT projection. [] if not confidently parseable."""
    s = _strip_comments(sql or "")
    depth, sel = 0, None
    for m in re.finditer(r"[()]|\bselect\b|\bfrom\b", s, re.IGNORECASE):
        t = m.group(0).lower()
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif t == "select" and depth == 0:
            sel = m.end()
    if sel is None:
        return []
    depth, frm = 0, None
    for m in re.finditer(r"[()]|\bfrom\b", s[sel:], re.IGNORECASE):
        t = m.group(0).lower()
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif t == "from" and depth == 0:
            frm = sel + m.start(); break
    if frm is None:
        return []
    items = []
    for raw in _split_top_commas(s[sel:frm]):
        it = raw.strip()
        if not it:
            continue
        m = re.search(r"\bas\s+([`\"]?)([A-Za-z_][A-Za-z0-9_]*)\1\s*$", it, re.IGNORECASE)
        if m:
            items.append((it[:m.start()].strip(), m.group(2)))
        else:
            items.append((it, None))
    return items


def check_output_naming(sql: str):
    """Lint outermost SELECT output columns against role-based naming (sql_style §D). All WARN."""
    out = []
    RULE = "sql_style §D (naming)"
    for expr, alias in _final_select_items(sql):
        e = expr.strip()
        low = e.lower()
        bare_col = re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)?", e) is not None
        if alias is None:
            if not bare_col:
                out.append(Finding("WARN", "name_missing_alias",
                                   f"output expression `{e[:40]}` has no AS alias — name it.", RULE))
            continue
        a = alias.lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", alias):
            out.append(Finding("WARN", "name_not_snake", f"alias `{alias}` is not snake_case.", RULE))
        is_ratio = ("safe_divide" in low or re.search(r"\)\s*/\s*", e) is not None
                    or a.endswith(("_rate", "_share", "_growth")) or a.startswith(("pct", "avg_", "median"))
                    or "_per_" in a)
        if is_ratio:
            continue
        entity_count = bool(re.search(rf"count\s*\(\s*distinct[^)]*{re.escape(ENTITY_KEY)}", low)) or "countif(" in low
        if entity_count and not ("customers" in a or a.startswith("num_")):
            out.append(Finding("WARN", "name_count_suffix",
                               f"customer count aliased `{alias}` — use a *_customers (or num_*) name.", RULE))
        sums_money = any(re.search(rf"sum\s*\(\s*[^)]*{re.escape(m)}", low) is not None
                         for m in MONEY_COLUMNS)
        if sums_money and not a.endswith("_revenue"):
            out.append(Finding("WARN", "name_money_suffix",
                               f"revenue sum aliased `{alias}` — use a *_revenue name.", RULE))
    return out


# ---------------------------------------------------------------------------
def lint_sql(sql: str, out_columns=None):
    """Return a list of Findings (possibly empty). `out_columns` = executed result headers (lowercased),
    if the query was run — enables the PII output check."""
    f = []
    s = _strip_comments(sql or "")
    low = s.lower()

    touches_fact = any(t in low for t in FACT_TABLES)
    touches_dim = DIM in low

    # 1) fact table must be bridged through the dimension (scope + identity).  [semantic_model: mandatory bridge]
    if touches_fact and not touches_dim:
        # onboarding-funnel exception: counting signup_id on a pre-activation milestone
        onboarding_exc = "signup_id" in low and "signup" in low
        if not onboarding_exc:
            f.append(Finding("ERROR", "fact_unbridged",
                             f"query hits a fact table without joining {DIM} — sums over out-of-scope "
                             "(test/fraud) customers.", "glossary: Mandatory scope (bridge)"))

    # 2) dimension must carry the mandatory scope filters.  [glossary: Mandatory scope]
    if touches_dim:
        for i, col in enumerate(SCOPE_COLUMNS):
            if col.lower() not in low:
                # Keep the historic codes for the default two-column policy so
                # existing goldens/selftests keep passing; extras get a generic code.
                if col == "is_test":
                    code = "missing_test_scope"
                elif col == "is_fraud":
                    code = "missing_fraud_scope"
                else:
                    code = f"missing_{col}_scope"
                f.append(Finding("ERROR", code,
                                 f"query touches {DIM} without a {col} = FALSE filter.",
                                 "glossary: Mandatory scope"))

    # 3) counting hygiene.  [sql_style §B]
    if re.search(r"count\s*\(\s*\*\s*\)", low):
        f.append(Finding("WARN", "count_star",
                         f"COUNT(*) used — prefer COUNT(DISTINCT {ENTITY_KEY}).", "sql_style §B (counting)"))
    if re.search(r"\bcountif\s*\(", low):
        f.append(Finding("WARN", "countif_used",
                         f"COUNTIF(...) counts rows, not distinct customers — prefer "
                         f"COUNT(DISTINCT IF(<flag>, {ENTITY_KEY}, NULL)).", "sql_style §B (counting)"))

    # 4) subset flag in WHERE under a DIMENSION group by → drops zero-buckets.  [sql_style §B]
    if "group by" in low and not _last_group_by_is_time_only(low):
        for _wstart, wtext in _where_clauses(low):
            hit = None
            for flag in SUBSET_FLAGS:
                if re.search(rf"(?<![.\w])(?:\w+\.)?{flag}\b", wtext):
                    hit = flag
                    break
            if hit:
                f.append(Finding("WARN", "where_drops_zero_buckets",
                                 f"'{hit}' filtered in WHERE with a dimension GROUP BY — use "
                                 f"COUNT(DISTINCT IF({hit}, {ENTITY_KEY}, NULL)) to keep zero groups.",
                                 "sql_style §B (per-group subset count)"))
                break

    # 5) PII in output — delegated to the single PII policy module.  [tools/pii_guard.py]
    for pf in _load_pii_guard().scan_sql(sql or "", out_columns):
        f.append(Finding("ERROR", "pii_output", pf.message + ".", "PII guard (tools/pii_guard.py)"))

    # 6) output-column naming (WARN).  [sql_style §D]
    f.extend(check_output_naming(sql or ""))
    return f


def main() -> int:
    sql = sys.stdin.read()
    findings = lint_sql(sql)
    for fi in findings:
        print(fi)
    if not findings:
        print("OK: no lint findings")
    return 1 if any(fi.level == "ERROR" for fi in findings) else 0


# --- self-test -------------------------------------------------------------
def _selftest() -> int:
    cases = [
        # (sql, out_cols, expected ERROR codes)
        ("SELECT channel, SUM(order_amount) FROM `p.d.fct_orders_daily` GROUP BY 1",
         None, {"fact_unbridged"}),
        ("WITH scoped AS (SELECT customer_id FROM `p.d.dim_customer_latest` "
         "WHERE is_test=FALSE AND is_fraud=FALSE) "
         "SELECT SUM(o.order_amount) AS total_revenue FROM `p.d.fct_orders_daily` o "
         "JOIN scoped s USING (customer_id)", None, set()),
        ("SELECT country, COUNT(DISTINCT customer_id) AS customers FROM `p.d.dim_customer_latest` GROUP BY 1",
         None, {"missing_test_scope", "missing_fraud_scope"}),
        ("SELECT segment, COUNT(DISTINCT customer_id) AS customers FROM `p.d.dim_customer_latest` "
         "WHERE is_test=FALSE AND is_fraud=FALSE GROUP BY segment", None, set()),
        ("SELECT customer_id, email FROM `p.d.dim_customer_latest` "
         "WHERE is_test=FALSE AND is_fraud=FALSE", None, {"pii_output"}),
    ]
    ok = True
    for i, (sql, cols, want) in enumerate(cases):
        got = {f.code for f in lint_sql(sql, cols) if f.level == "ERROR"}
        status = "PASS" if got == want else "FAIL"
        ok = ok and got == want
        print(f"  case {i}: {status}  want={sorted(want)} got={sorted(got)}")

    name_cases = [
        ("SELECT country, COUNT(DISTINCT customer_id) AS customers FROM t GROUP BY country", set()),
        ("SELECT SUM(order_amount) AS total_revenue FROM t", set()),
        ("SELECT SAFE_DIVIDE(SUM(order_amount), COUNT(DISTINCT customer_id)) AS revenue_per_customer FROM t", set()),
        ("SELECT COUNTIF(is_active_month) AS active FROM t", {"name_count_suffix"}),
        ("SELECT SUM(order_amount) AS money FROM t", {"name_money_suffix"}),
    ]
    for i, (sql, want) in enumerate(name_cases):
        got = {f.code for f in check_output_naming(sql)}
        status = "PASS" if got == want else "FAIL"
        ok = ok and got == want
        print(f"  name case {i}: {status}  want={sorted(want)} got={sorted(got)}")

    print("SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
