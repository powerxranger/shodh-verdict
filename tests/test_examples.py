"""Hand-written examples are independent of the frozen-set generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verdict.config import ReviewConfig
from verdict.models import Bundle
from verdict.pipeline import review_bundle

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize("name", ["manual_bundle", "manual_bundle_defect"])
def test_hand_written_example_has_expected_verdict(name):
    data = json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    bundle = Bundle.model_validate(data)
    report = review_bundle(bundle, ReviewConfig.from_env(), use_cache=False)
    assert report.status == bundle.expected_status, report.summary

    kinds = {f.kind for f in report.findings}
    for kind in bundle.expected_finding_kinds:
        assert kind in kinds


def test_defect_example_carries_a_counterexample():
    data = json.loads((EXAMPLES / "manual_bundle_defect.json").read_text(encoding="utf-8"))
    report = review_bundle(Bundle.model_validate(data), ReviewConfig.from_env(), use_cache=False)
    blockers = [f for f in report.findings if f.severity == "blocker"]
    assert blockers
    assert any(f.counterexample is not None and f.expected_route != f.actual_route
               for f in blockers)
