# v0 baseline checkpoint (orphan commit `v0-baseline`)

This commit preserves the **initial working checkpoint** of the assessment: a deliberately naive reviewer that checks rule-ID presence and numeric substring overlap only.

It has no decision-program compilation, no boundary-partition equivalence, no precedence analysis and no counterexample generation. It is kept solely so the controlled evaluation in `EVALUATION.md` can compare it against the final implementation on the same frozen set.

- Naive reviewer: `checkpoints/baseline/naive_reviewer.py`
- Measured result: 10/18 correct vs the final implementation's 18/18.
- The final implementation lives on branch `master` at tag `v1-final`.

This is a deliberately limited checkpoint, not a production reviewer.
