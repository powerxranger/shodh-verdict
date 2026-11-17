# Deliberate fault injection log

Both entries are **deliberately injected faults**, introduced during development, run against the frozen synthetic cases, diagnosed, fixed and covered by regression tests. The `before.json` / `after.json` files are the actual captured reports from `scripts/capture_case.py`. No failure history is invented.

## Fault 1 — unit normalisation removed

- Injection: early `return value, None` in `verdict/programs.py::to_base_units`.
- Case: `hours_equivalent` (requirement `0.5 hours` ≡ `30 minutes` in other artifacts).
- Command: `python scripts/capture_case.py hours_equivalent debug/fault_1_unit_normalization/before.json`
- Observed: `CHANGES_REQUIRED`, 3 × `CHANGED_THRESHOLD`.
- Diagnosis: 0.5 was compared against 30 because unit conversion was skipped.
- Fix: restore minute conversion; make unit consistency check semantic (converted values), not lexical.
- Captured after: `PASS`, 0 findings.
- Regression: `tests/test_regressions.py::test_registry_fault_1_hours_are_normalised_to_minutes`.

## Fault 2 — workflow false branch not negated

- Injection: `walk(node.false_next, AND(path, guard), ...)` in `verdict/compilers.py::compile_workflow`.
- Case: `pass` (the unchanged aligned base bundle).
- Command: `python scripts/capture_case.py pass debug/fault_2_false_branch_negation/before.json`
- Observed: `CHANGES_REQUIRED`, 5 findings including 2 × `MISSING_BRANCH` and `CHANGED_THRESHOLD`.
- Diagnosis: both decision branches accumulated the same positive guard, breaking path coverage.
- Fix: restore `AND(path, NOT(guard))` on the false edge.
- Captured after: `PASS`, 0 findings.
- Regression: `tests/test_regressions.py::test_regression_fault_2_false_workflow_branch_is_negated`.

See `EVALUATION.md` sections 4 and 5 for the quoted outputs and full narrative.
