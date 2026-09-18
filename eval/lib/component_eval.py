"""component_eval.py — isolate ONE decision, so a small brain edit doesn't need a full end-to-end run.

The full eval (run_eval.py) is slow and costs money: it runs every golden THROUGH the agent and executes SQL.
But most brain edits only affect ONE decision — routing, the time window, the output shape. A component eval
asks the model that ONE question in isolation and checks it deterministically. Fast, cheap, focused signal.

Use it as the FIRST check after a small brain change; only escalate to the full eval when it warrants it.

Three example components (add your own):
  C1 ROUTE   — given a question, which table? (check against the expected table)
  C2 TIME    — given a question with a date phrase, what window? (check the parsed bounds)
  C3 SHAPE   — given a question, what output columns/grain? (check the projection shape)

This template ships the harness + a deterministic ROUTE checker you can run offline (no LLM) as an example;
wire the LLM call where marked to grade C1/C2/C3 for real.
"""
from __future__ import annotations

from dataclasses import dataclass


# --- component test cases (EDIT for your schema) ---------------------------
ROUTE_CASES = [
    # (question, expected_table)
    ("how many active customers do we have?", "dim_customer_latest"),
    ("total revenue in 2025", "fct_orders_daily"),
    ("monthly active customers trend", "fct_product_usage_monthly"),
]


@dataclass
class ComponentResult:
    component: str
    passed: int
    total: int

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _route_offline(question: str) -> str:
    """A cheap deterministic router used to demonstrate the harness WITHOUT an LLM.
    In production, replace this with a single LLM call that returns just the table name — the component eval
    then measures the model's routing in isolation from the rest of the loop."""
    q = question.lower()
    if "month" in q:
        return "fct_product_usage_monthly"
    if "revenue" in q or "order" in q or "sales" in q:
        return "fct_orders_daily"
    return "dim_customer_latest"


def run_route(router=_route_offline) -> ComponentResult:
    passed = 0
    for q, expected in ROUTE_CASES:
        got = router(q)
        ok = got == expected
        passed += ok
        print(f"  [{'ok' if ok else 'XX'}] route: {q!r:50} -> {got}  (want {expected})")
    return ComponentResult("route", passed, len(ROUTE_CASES))


def main(argv=None) -> int:
    import sys
    argv = argv or sys.argv[1:]
    component = argv[0] if argv else "route"
    if component == "route":
        r = run_route()
    else:
        print(f"unknown component '{component}' (available: route)")
        return 2
    print(f"COMPONENT {r.component}: {r.passed}/{r.total} = {r.rate:.0%}")
    return 0 if r.passed == r.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
