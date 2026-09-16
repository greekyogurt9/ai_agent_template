# Thin wrappers over the eval harness. `make help` lists targets.
# The trust loop, cheapest → most expensive:  check → component → eval
.PHONY: help check component eval selftests snapshots restore config prompt

PY := PYTHONPATH=. python3

help:
	@echo "Analytics Agent Template — targets:"
	@echo "  make config              print resolved config (warehouse/model/budgets)"
	@echo "  make prompt              assert brain is live + print prompt size/hash"
	@echo "  make check               FREE  — brain-live + linter/PII/comparator self-tests"
	@echo "  make component [C=route] CHEAP — isolate ONE decision after a small brain edit"
	@echo "  make eval RUN=<id> [TIER=core]   FULL — goldens through the agent, executed + scored"
	@echo "  make snapshots           list saved brain snapshots + their hash"
	@echo "  make restore RUN=<id>    revert brain/ to a snapshot (undo a bad change)"

config:
	@$(PY) -m agent.config

prompt:
	@$(PY) -m agent.prompt

check:
	@$(PY) -m eval.run_eval check

selftests:
	@$(PY) tools/lint_sql.py --selftest
	@$(PY) tools/pii_guard.py --selftest
	@$(PY) -m eval.lib.comparator --selftest

C ?= route
component:
	@$(PY) -m eval.run_eval component $(C)

TIER ?=
eval:
	@test -n "$(RUN)" || (echo "usage: make eval RUN=<id> [TIER=core]"; exit 2)
	@$(PY) -m eval.run_eval run $(RUN) $(TIER)

snapshots:
	@$(PY) -m eval.lib.snapshot list

restore:
	@test -n "$(RUN)" || (echo "usage: make restore RUN=<id>"; exit 2)
	@$(PY) -m eval.lib.snapshot restore $(RUN)
