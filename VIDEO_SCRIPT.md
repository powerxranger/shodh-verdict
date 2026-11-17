# 2-minute video script

Target: ~2:00 at a measured, calm pace. Record screen + webcam if possible; show the repo and one CLI run. Do not read verbatim — use as cue cards.

---

**0:00–0:15 — Introduction**

"Hi, I'm Krish Aggarwal, an AI/ML engineering candidate. I built **Verdict**, a Python application that reviews whether a written policy, a structured spec, a decision workflow and linked Python code actually agree. It returns PASS, CHANGES_REQUIRED or INCOMPLETE with evidence — not just a similarity score."

**0:15–0:55 — The project and the core idea**

"The key idea is that all four artifacts compile into one decision program over a ticket — category, urgency and waiting time. I then build a finite input domain from every threshold in every artifact. For each numeric boundary I test the boundary itself, points either side and the intervals between boundaries; for categories I test every constant, missing and an unlisted value. For this supported language that domain is *complete*, so agreement means real equivalence, and disagreement gives a concrete ticket with expected and actual routes."

*Show: `python -m verdict --demo` and the JSON counterexample.*

"Approvals are a firewall: only top-level approval metadata can change effective requirements. A prose claim like 'APPROVED by product' is flagged and ignored, and contradictory approvals become a blocker rather than silently picking a version."

**0:55–1:25 — Model trust and evaluation**

"The model client is behind an interface with a deterministic fake for reproducible tests and an optional HTTP hook. Its output is validated: invented references, unresolved evidence, truncated JSON, conflicting claims and coverage overclaims are rejected. Model findings are advisory unless they pass a strict evidence gate."

"On a frozen 18-case evaluation set, Verdict gets 18 out of 18 correct while a preserved naive ID-and-substring baseline gets 10. I also ran an ablation disabling the exhaustive domain — it produced a false PASS on one case and lost counterexamples on others, which is the concrete benefit of the mechanism."

*Show: `evals/results.json`, `EVALUATION.md` table.*

**1:25–1:50 — Debugging and rigour**

"I preserved two deliberate fault-injection cycles: removing unit conversion and breaking the workflow's false-branch negation. Each has the actual failing output, a diagnosis, a focused fix and a regression test. Code inspection, syntax checking and execution are separate, and execution is off by default."

**1:50–2:00 — Why Shodh AI**

"I want to join Shodh AI because this assessment matches how I like to work: define contracts, make correctness checkable, and be honest about what hasn't been verified. I'd bring that discipline to your AI/ML engineering team. Thank you."

---

## Recording checklist

- [ ] Keep links to Drive files set to **Anyone with the link → Viewer**.
- [ ] Open both links in a logged-out/incognito window to confirm no access request.
- [ ] Repo public, README visible, no secrets in files or history.
- [ ] Keep under 2:05; trim section 2 if needed.
