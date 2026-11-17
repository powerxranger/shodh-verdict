# Suggested resume framing

Use 2–3 of these under a **Projects** heading titled *Verdict — AI-assisted specification reviewer (Python)*. Adjust to fit your real resume style; don't claim anything you can't discuss.

- Built a Python reviewer that compiles written requirements, structured specs, workflow graphs and AST-inspected Python into one decision program, producing evidence-backed `PASS` / `CHANGES_REQUIRED` / `INCOMPLETE` verdicts.
- Designed an **exhaustive boundary-partition equivalence engine** using exact rational arithmetic; proved equivalence or emitted concrete counterexamples (expected vs actual routes) across 27–45 representative inputs per case.
- Implemented an approval-authority firewall: revision-scoped changes, deterministic change ordering, contradiction detection, and rejection of approval claims embedded in prose or code comments.
- Built a model-client interface with a deterministic fake and optional HTTP backend; validated reports for invented references, unresolved evidence, truncated/malformed JSON, conflicting claims and coverage overclaims with bounded retries and token budgets.
- Created an 18-case SHA-256-frozen evaluation suite: 18/18 correct vs a preserved naive baseline's 10/18; a controlled ablation disabling equivalence caused a false PASS, quantifying the mechanism's value.
- Documented two deliberate fault-injection cycles with captured failing output, diagnosis, focused fixes and regression tests; 54 pytest tests passing.
- Stack: Python 3.12, Pydantic, pytest, AST, exact `Fraction` arithmetic, stdlib `urllib`; CPU-only, reproducible, no paid services.

## One-line project description for the form

> Verdict — a deterministic, evidence-backed reviewer that proves whether specs, workflows and linked Python implement written policies, with model output treated as strictly validated annotations.

## Interview talking points

1. Why ID/substring matching fails (show the baseline's false PASS on `approved_25_ignored`).
2. Why the finite domain is complete for the supported language (boundary argument).
3. Why the model cannot change status or approval authority.
4. Why `INCOMPLETE` is a first-class outcome instead of a forced PASS.
5. What the ablation proved and what it did not.
