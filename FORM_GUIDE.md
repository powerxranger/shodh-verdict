# Submission / form guide

The hiring team clarified that the **same assessment** is used for both full-time and internship pathways, and that the "Intern" wording in the earlier email, PDF and form does not limit consideration. No additional submission is needed if you already submitted.

## Role selection

- Select the **relevant technical role** for your profile. If the form offers **AI/ML Engineer** (full-time), choose that if you want to be considered for full-time.
- If the only available option is **AI/ML Engineer Intern**, select it — the team explicitly confirmed this does not restrict you to the internship pathway.
- The assessment content is identical either way. Your performance, experience and overall profile determine the pathway.

## Submission checklist

- [ ] Public GitHub repo: `shodh-verdict` (branch `master` @ `v1-final`; baseline preserved at `v0-baseline`).
- [ ] `README.md` renders correctly on GitHub; docs and `EVALUATION.md` are visible.
- [ ] Google Drive **2-minute video** link: Anyone with the link → **Viewer**.
- [ ] Google Drive **resume** link: Anyone with the link → **Viewer**.
- [ ] Open both links in an incognito window to confirm no access request.
- [ ] Fill remaining form fields consistently with your resume.
- [ ] Submit before **18 Nov 2026, 11:59 PM IST**.

## What to highlight in free-text fields (if any)

> I built Verdict end to end: anchored input contracts, a documented source-language parser, a restricted-Python AST inspector, and an exhaustive boundary-partition equivalence engine that produces concrete counterexamples. Model output is treated as strictly validated annotations, never as authority. On an 18-case SHA-256 frozen evaluation set it scores 18/18 versus 10/18 for a preserved naive baseline; an ablation disabling equivalence produces a false PASS, quantifying the mechanism's value. Two deliberate fault injections are documented with real failing output, fixes and regression tests. CI reruns tests, the frozen evaluation and the ablation on every push.

Keep it short if the field is limited — the repo and video carry the detail.

## Useful verification commands before submitting

```powershell
python -m pytest
python scripts/run_eval.py
python -m verdict --demo                                             # required JSON report
python -m verdict evals/frozen/cases/code_wrong.json --format text  # human-readable counterexample
git status --short   # must be clean
git log --oneline --decorate --all
```

If a recruiter asks to see the app work, the two `python -m verdict` commands above are enough: the first shows the required JSON report contract, the second shows the same engine's finding in plain English. Both are CLI runs — there is no frontend, and none was requested.
