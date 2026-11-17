# Suggested resume framing

Use 3–4 of these under a **Projects** heading titled *Verdict — AI/ML systems & evaluation engineer (Python)*. The framing is intentionally full-time ready while still credible for an internship. Adjust to your real resume style; don't claim anything you can't discuss.

- Built a Python reviewer that compiles written requirements, structured specs, workflow graphs and AST-inspected Python into one decision program, producing evidence-backed `PASS` / `CHANGES_REQUIRED` / `INCOMPLETE` verdicts.
- Designed an **exhaustive boundary-partition equivalence engine** using exact rational arithmetic; proved equivalence or emitted concrete counterexamples (expected vs actual routes) across 27–45 representative inputs per case.
- Implemented an approval-authority firewall: revision-scoped changes, deterministic change ordering, contradiction detection, and rejection of approval claims embedded in prose or code comments.
- Built a model-client interface with a deterministic fake and optional HTTP backend; validated reports for invented references, unresolved evidence, truncated/malformed JSON, conflicting claims and coverage overclaims with bounded retries and token budgets.
- Created an 18-case SHA-256-frozen evaluation suite: 18/18 correct vs a preserved naive baseline's 10/18; a controlled ablation disabling equivalence caused a false PASS, quantifying the mechanism's value.
- Documented two deliberate fault-injection cycles with captured failing output, diagnosis, focused fixes and regression tests; 60 pytest tests passing.
- Stack: Python 3.12, Pydantic, pytest, AST, exact `Fraction` arithmetic, stdlib `urllib`; CPU-only, reproducible, no paid services.
- Owned the delivery pipeline end to end: versioned input contracts, CLI + library API, pinned dependencies, GitHub Actions CI, frozen evaluation set and documented extension path — the same practices expected in a full-time engineering role.
- Kept the required JSON report contract as the default output while adding an opt-in human-readable view (`--format text` / `report.to_text()`) rendered from the same report object, so the two formats cannot diverge.
- Designed for failure rather than the happy path: bounded model retries/token budgets, template-safe prompt boundaries, untrusted Python isolated behind an opt-in subprocess, and content-addressed caching that invalidates when approvals change.

## One-line project description for the form

> Verdict — an evidence-backed AI/ML reviewer that proves whether specs, workflows and linked Python implement written policies, with model output treated as strictly validated annotations. Built end to end with tests, CI, frozen evaluation and debugging evidence.

## Interview talking points

1. Why ID/substring matching fails (show the baseline's false PASS on `approved_25_ignored`).
2. Why the finite domain is complete for the supported language (boundary argument).
3. Why the model cannot change status or approval authority.
4. Why `INCOMPLETE` is a first-class outcome instead of a forced PASS.
5. What the ablation proved and what it did not.
6. How you'd extend the supported language in production (new operators → new domain construction → new tests instead of new prompts).
7. Why you'd be comfortable owning a service feature end to end, and what you'd still want to learn from a senior team.
