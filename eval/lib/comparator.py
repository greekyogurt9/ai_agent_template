"""comparator.py — the OBJECTIVE eval: does the agent's result match the golden result?

Why not a plain diff? Two reasons this template exists to teach:

  1. Warehouse float SUMs are NOT bit-reproducible. `SUM(order_amount)` can return 1234.5600000001 one run
     and 1234.56 the next. An exact string/EXCEPT-DISTINCT diff on rounded floats gives FALSE FAILURES.
  2. The agent may name a column slightly differently than your reference ("total_revenue" vs "revenue").

So we compare VALUES within a relative tolerance, KEYED by the dimension columns, and we are insensitive to
column NAMES (we align by position/role, not by header string). This is the single most important piece of
making an eval trustworthy — a noisy comparator makes every score meaningless.

Rows are compared as: split each row into dimension cells (non-numeric) and metric cells (numeric). Build a
key from the dimension cells; match rows by key; compare metric cells with relative tolerance.
"""
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_REL_TOL = 1e-6      # 0.0001% — generous enough for float noise, tight enough to catch real diffs
DEFAULT_ABS_TOL = 1e-6      # for values near zero


def _is_number(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _num(x) -> float:
    return float(x)


def _split_row(row: list):
    """(dimension_key_tuple, [metric_floats]) for one result row."""
    dims, metrics = [], []
    for cell in row:
        if _is_number(cell):
            metrics.append(_num(cell))
        else:
            dims.append(str(cell).strip().lower())
    return tuple(dims), metrics


def _close(a: float, b: float, rel: float, abs_: float) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


@dataclass
class CompareResult:
    passed: bool
    reason: str
    n_rows_expected: int = 0
    n_rows_got: int = 0


def compare(expected_rows: list, got_rows: list,
            rel_tol: float = DEFAULT_REL_TOL, abs_tol: float = DEFAULT_ABS_TOL) -> CompareResult:
    """Compare two result sets (each a list of rows; each row a list of cells).

    Header rows should be stripped by the caller. Order-insensitive: rows are matched by their
    dimension-cell key, so a differently-ordered result still passes.
    """
    exp_map, got_map = {}, {}
    for r in expected_rows:
        k, m = _split_row(r)
        exp_map[k] = m
    for r in got_rows:
        k, m = _split_row(r)
        got_map[k] = m

    if set(exp_map) != set(got_map):
        missing = set(exp_map) - set(got_map)
        extra = set(got_map) - set(exp_map)
        return CompareResult(False,
                             f"dimension keys differ (missing={sorted(missing)[:3]}, extra={sorted(extra)[:3]})",
                             len(expected_rows), len(got_rows))

    for k in exp_map:
        em, gm = exp_map[k], got_map[k]
        if len(em) != len(gm):
            return CompareResult(False, f"row {k!r}: metric count {len(em)} vs {len(gm)}",
                                 len(expected_rows), len(got_rows))
        for i, (a, b) in enumerate(zip(em, gm)):
            if not _close(a, b, rel_tol, abs_tol):
                return CompareResult(False, f"row {k!r} metric[{i}]: {a} vs {b} (> tol)",
                                     len(expected_rows), len(got_rows))

    return CompareResult(True, "match", len(expected_rows), len(got_rows))


# --- self-test -------------------------------------------------------------
def _selftest() -> int:
    ok = True

    # float noise within tolerance → PASS
    r = compare([["1234.56"]], [["1234.5600000001"]])
    ok = ok and r.passed
    print("  float noise:", "PASS" if r.passed else f"FAIL ({r.reason})")

    # reordered rows, same data → PASS (order-insensitive)
    exp = [["a", "10"], ["b", "20"]]
    got = [["b", "20"], ["a", "10"]]
    r = compare(exp, got)
    ok = ok and r.passed
    print("  reordered:", "PASS" if r.passed else f"FAIL ({r.reason})")

    # a real difference → FAIL
    r = compare([["a", "10"]], [["a", "11"]])
    ok = ok and not r.passed
    print("  real diff:", "PASS" if not r.passed else "FAIL (should have failed)")

    # a missing dimension bucket → FAIL
    r = compare([["a", "1"], ["b", "2"]], [["a", "1"]])
    ok = ok and not r.passed
    print("  missing bucket:", "PASS" if not r.passed else "FAIL (should have failed)")

    print("COMPARATOR SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
