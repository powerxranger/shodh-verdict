"""Regression tests for the two deliberately injected and repaired faults.

See debug/ for the captured before/after reports and diagnosis notes.
"""

from scripts.make_demo import make_bundle
from verdict.config import ReviewConfig, UNIT_TO_MINUTES
from verdict.programs import to_base_units
from verdict.pipeline import review_bundle


def test_registry_fault_1_hours_are_normalised_to_minutes():
    """Fault 1: unit conversion was removed, causing false CHANGED_THRESHOLD."""
    value, warning = to_base_units(0.5, "waiting_minutes", "hours")
    assert warning is None
    assert abs(value - 30.0) < 1e-9
    assert abs(0.5 * UNIT_TO_MINUTES["hours"] - 30.0) < 1e-9

    bundle = make_bundle("hours_equivalent")
    report = review_bundle(bundle, ReviewConfig.from_env(), use_cache=False)
    assert report.status == "PASS", report.summary
    assert not any(f.kind == "CHANGED_THRESHOLD" for f in report.findings)


def test_regression_fault_2_false_workflow_branch_is_negated():
    """Fault 2: false branch reused the positive guard, breaking routing."""
    bundle = make_bundle("pass")
    report = review_bundle(bundle, ReviewConfig.from_env(), use_cache=False)
    assert report.status == "PASS", report.summary
    assert not any(f.kind in ("MISSING_BRANCH", "CHANGED_THRESHOLD")
                   for f in report.findings)
    assert report.coverage.partitions_tested > 0
