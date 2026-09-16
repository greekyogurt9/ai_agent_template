I built an AI analytics agent that takes a one-line question and turns it into a stakeholder-ready answer — from SQL generation to deep-dive analysis to the final deck.

The interesting part wasn’t getting an LLM to write SQL.

It was figuring out what makes an analytics agent trustworthy enough to put a number in front of leadership.

Here are the biggest things I learned.

**1. Use the LLM for reasoning, not everything.**

My first instinct was to let the model handle routing, business rules, SQL generation, validation, formatting — basically everything.

That made the system flexible, but also fragile.

I flipped the architecture: make as much of the workflow deterministic as possible and use the LLM where genuine reasoning is required.

The workflow is the recipe. The LLM is the chef making the judgment calls.

Less LLM → more control → more trust.

**2. If a rule can be enforced in code, don’t leave it in a prompt.**

Business rules buried in documentation are suggestions.

So I moved them into hard gates wherever possible:

→ SQL linting and counting-pattern checks
→ PII guards that block sensitive queries
→ Deterministic validation before LLM review
→ Review gates that escalate to an LLM only when necessary

A rule in prose is hope.

A rule in code is enforcement.

**3. Don’t make the model remember what the system can look up.**

I initially stored things like column names and category values in the agent’s knowledge base.

That worked — until the schema changed.

The model would confidently query columns that no longer existed or use category values that had been renamed.

Now schema metadata and real category values are fetched live at query time.

No stale memory. Less drift. Fewer hallucinations.

**4. “It works” is not an evaluation strategy.**

An agent can produce impressive demos while quietly getting important numbers wrong.

So I built a sandboxed evaluation framework with two layers:

→ Objective evals: golden questions, generated SQL, warehouse execution, and comparison against verified answers.

→ Subjective evals: LLM-based critics for things like analytical reasoning and deck quality, evaluated against explicit rubrics and pass thresholds.

The eval environment is isolated from the live workflow, so testing can’t accidentally mutate production.

**5. Full end-to-end evals shouldn’t be your only evals.**

Running the entire agent for every small change is slow and expensive.

So I added component-level evals that test individual decisions:

→ Did it select the right table?
→ Did it choose the right time window?
→ Did it apply the right business rule?
→ Did it produce the expected output shape?

Fast feedback for small changes. Full runs when they’re actually warranted.

**6. Version the agent’s “brain”, not just the code.**

Every evaluation run snapshots the knowledge base and test set and records a version hash alongside the pass rate.

That means I can answer:

“What changed?”

“Did it make the agent better or worse?”

“And what was the last known-good version?”

You can’t reliably improve an agent if you can’t reproduce what it knew when it failed.

**7. Fix patterns, not individual failures.**

This was probably the biggest learning.

When an agent gets one question wrong, it’s tempting to patch that exact case.

But 50 wrong answers may actually come from one structural problem.

So instead of fixing failures one by one, I look for patterns across evals and fix the underlying cause.

One structural fix beats fifty patches.

**8. Trustworthiness has to extend beyond the answer.**

The agent doesn’t stop at answering questions.

For a “why did X change?” investigation, it can run the analyst workflow end-to-end:

→ Root-cause analysis
→ Cohort analysis
→ Survival analysis
→ Reconciliation back to the headline number
→ Stakeholder-ready presentation

And because the system is autonomous, I also added operational guardrails — critic loops, cost ceilings, and email allowlists.

The goal isn’t just:

“Can the agent produce an answer?”

It’s:

“Can I trust the entire path from question → analysis → decision-ready output?”

**The biggest mindset shift for me:**

The interesting engineering in AI agents isn’t the prompt.

It’s everything around the prompt.

Deterministic-first design.
Hard gates over soft rules.
Live metadata over stale memory.
Sandboxed evals.
Component-level testing.
Versioned rollbacks.
Systematic error hunting.
Operational guardrails.

The LLM is the easy part.

Still iterating. If you’re building agents on your own data, I’d love to compare notes on how you keep them honest. 👇

#AI #DataEngineering #LLM #Analytics #AgenticAI #DataScience
