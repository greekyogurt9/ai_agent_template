"""critic.py — the SUBJECTIVE eval: rubric-scored LLM review for things with no single right answer.

The objective comparator (comparator.py) handles "is the number right?" But some outputs have no golden SQL:
a deep dive's reasoning, a stakeholder deck's clarity, whether an answer's caveat is the RIGHT caveat. For
those, score against an explicit RUBRIC with an LLM critic and a hard pass bar.

Two disciplines make a critic trustworthy rather than a rubber stamp:
  1. An EXPLICIT rubric (dimensions + what each score means) — not "rate this 1-10, vibes."
  2. A HARD pass bar and, for the highest-stakes uses, a caps rule (a fatal flaw caps the score no matter how
     good everything else is). This stops a polished-but-wrong artifact from passing.

This file is a SKELETON: it defines the rubric and the scoring contract; wire your LLM where marked.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --- the rubric (EDIT for your artifact type) ------------------------------
RUBRIC = {
    "correctness":   "Are the claims supported by the data? Any unverified assertion caps the score at 8.5.",
    "answers_the_q": "Does it actually answer what was asked (not an adjacent question)?",
    "scope_honesty": "Are caveats/limitations stated plainly, not buried?",
    "clarity":       "Would a non-technical stakeholder understand it in one read?",
    "no_overclaim":  "No causal language from correlational evidence; no over-precision.",
}
PASS_BAR = 9.0          # tune per use; deck reviews often sit higher (e.g. 9.8)
CAPS_AT = 8.5           # a fatal flaw (see rubric) caps the total here


@dataclass
class CriticResult:
    score: float
    passed: bool
    per_dimension: dict = field(default_factory=dict)
    blockers: list = field(default_factory=list)
    notes: str = ""


def _build_prompt(artifact_text: str, question: str) -> str:
    lines = [
        "You are a strict senior reviewer. Score the ARTIFACT against the RUBRIC.",
        "Return one JSON object: {\"per_dimension\": {dim: score}, \"blockers\": [..], \"notes\": \"..\"}.",
        "Scores are 0.0-10.0 (one decimal). A blocker is a fatal flaw that must cap the total.",
        "",
        f"QUESTION: {question}",
        "",
        "RUBRIC:",
    ]
    for dim, desc in RUBRIC.items():
        lines.append(f"  - {dim}: {desc}")
    lines += ["", "ARTIFACT:", artifact_text]
    return "\n".join(lines)


def score(artifact_text: str, question: str = "", llm_json=None) -> CriticResult:
    """Score an artifact. `llm_json` is a callable(prompt)->dict returning the critic's JSON.
    If not provided (template mode), returns a neutral placeholder so the harness is runnable offline."""
    prompt = _build_prompt(artifact_text, question)
    if llm_json is None:
        # template mode — no LLM wired
        return CriticResult(score=0.0, passed=False, notes="[template mode] wire llm_json to score for real")

    data = llm_json(prompt)
    per = {k: float(v) for k, v in data.get("per_dimension", {}).items()}
    blockers = list(data.get("blockers", []))
    total = round(sum(per.values()) / len(per), 1) if per else 0.0
    if blockers:
        total = min(total, CAPS_AT)
    return CriticResult(score=total, passed=total >= PASS_BAR and not blockers,
                        per_dimension=per, blockers=blockers, notes=data.get("notes", ""))


if __name__ == "__main__":
    r = score("(example artifact)", "why did revenue fall?")
    print(f"score={r.score} passed={r.passed} notes={r.notes}")
