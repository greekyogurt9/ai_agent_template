"""agent.py — the ask loop: build prompt → budget check → invoke engine → parse → guard → save artifact.

This is the thin orchestrator. It does NOT write SQL itself; it hands the question, plus the live-brain system
prompt, to a headless LLM that runs the route→introspect→rules→SQL→review→run loop using its own tools. The
orchestrator's job is the *guarding*: budgets, cost logging, and saving a re-readable artifact.

    python3 -m agent.agent "how many active customers do we have?"

Swapping the LLM engine (CLI ↔ SDK) only touches `_invoke()`.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from agent import config, prompt


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Answer:
    status: str            # OK | NEEDS_CLARIFICATION | ERROR
    text: str              # the raw answer envelope from the model
    cost_usd: float
    duration_ms: int
    artifact: Path | None


def _slug(question: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")
    return (s[:60] or "question")


def _invoke(question: str, system_prompt: str) -> dict:
    """Call the headless LLM. Returns {'text', 'cost_usd', 'duration_ms'}.

    TEMPLATE: this shows the CLI shape (keyless — the CLI uses its own login). Replace with your engine.
    For an SDK, build the client here and return the same dict.
    """
    cmd = [
        config.LLM_CLI, "-p", question,
        "--append-system-prompt", system_prompt,
        "--allowedTools", "Bash",
        "--model", config.MODEL,
        "--output-format", "json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        # template mode: no engine wired yet
        return {"text": "[template mode] no LLM CLI configured — set AGENT_LLM_CLI in config.py",
                "cost_usd": 0.0, "duration_ms": 0}
    try:
        env = json.loads(proc.stdout)
        return {"text": env.get("result", proc.stdout),
                "cost_usd": float(env.get("total_cost_usd", 0.0)),
                "duration_ms": int(env.get("duration_ms", 0))}
    except json.JSONDecodeError:
        return {"text": proc.stdout or proc.stderr, "cost_usd": 0.0, "duration_ms": 0}


def _parse_status(text: str) -> str:
    m = re.search(r"^STATUS:\s*(\w+)", text, re.MULTILINE)
    return m.group(1).upper() if m else "OK"


class Analyst:
    """Session-scoped agent: tracks spend and enforces the session ceiling."""

    def __init__(self, budget_usd: float = config.MAX_SESSION_USD):
        self.budget_usd = budget_usd
        self.spent_usd = 0.0

    def ask(self, question: str) -> Answer:
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"session spend ${self.spent_usd:.2f} >= ceiling ${self.budget_usd:.2f}")

        system_prompt = prompt.build_agent_system_prompt()   # reads the LIVE brain every call
        res = _invoke(question, system_prompt)

        self.spent_usd += res["cost_usd"]
        if res["cost_usd"] > config.MAX_RUN_USD:
            print(f"[budget] WARN: single run ${res['cost_usd']:.2f} > ${config.MAX_RUN_USD}", file=sys.stderr)
        self._log_cost(res)

        status = _parse_status(res["text"])
        artifact = self._save_artifact(question, res["text"])
        return Answer(status=status, text=res["text"], cost_usd=res["cost_usd"],
                      duration_ms=res["duration_ms"], artifact=artifact)

    def _log_cost(self, res: dict) -> None:
        config.COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        new = not config.COST_LOG.exists()
        with config.COST_LOG.open("a") as fh:
            if new:
                fh.write("date\tmodel\tcost_usd\tsession_total_usd\n")
            fh.write(f"{date.today()}\t{config.MODEL}\t{res['cost_usd']:.4f}\t{self.spent_usd:.4f}\n")

    def _save_artifact(self, question: str, text: str) -> Path:
        d = config.AGENT_DIR / "runs"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{_slug(question)}_{date.today():%Y%m%d}.md"
        path.write_text(f"# {question}\n\n_brain {prompt.brain_hash()} · {date.today()}_\n\n{text}\n")
        return path


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print('usage: python3 -m agent.agent "your question"', file=sys.stderr)
        return 2
    ans = Analyst().ask(" ".join(argv))
    print(ans.text)
    if ans.artifact:
        print(f"\n[saved] {ans.artifact}  (${ans.cost_usd:.4f})", file=sys.stderr)
    return 0 if ans.status != "ERROR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
