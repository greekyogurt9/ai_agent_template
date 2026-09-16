"""Analytics agent (Layer 2) — a thin orchestrator over a live brain and external engines.

This package owns ONLY the orchestration. It reads the brain (../brain, ../tools) live on every run and is
measured by the eval harness (../eval). Nothing about the brain is baked in here — see prompt.verify_brain_is_live.
"""
