"""The frozen evaluation set is part of the test suite."""

import json
from pathlib import Path

import pytest

from scripts.run_eval import CASES_DIR, MANIFEST, verify_freeze
from verdict.config import ReviewConfig
from verdict.models import Bundle
from verdict.pipeline import review_bundle

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST.exists(), "run `python scripts/run_eval.py --freeze-only` first"
    return json.loads(MANIFEST.read_text())


def test_frozen_hashes_unchanged(manifest):
    assert verify_freeze(manifest) == []


@pytest.mark.parametrize("case_id", [
    "pass", "approved_25_pass", "approved_25_ignored", "unapproved_25_applied",
    "contradictory_approval", "omitted_requirement", "precedence_swapped",
    "missing_branch", "code_wrong", "unsupported_source", "injection_prose",
    "overlap_exceptions", "unit_mismatch", "hours_equivalent", "model_truncated",
    "model_invented_ref", "model_conflicting", "model_valid_finding",
])
def test_frozen_case(case_id, manifest):
    meta = manifest["cases"][case_id]
    bundle = Bundle.model_validate_json((CASES_DIR / f"{case_id}.json").read_text())
    report = review_bundle(bundle, ReviewConfig.from_env(**meta["config"]), use_cache=False)
    kinds = {f.kind for f in report.findings}
    assert report.status == meta["expected_status"], (case_id, report.summary, kinds)
    for kind in meta["expected_finding_kinds"]:
        assert kind in kinds, (case_id, kind, kinds)


def test_behavioral_mismatches_carry_concrete_counterexamples():
    bundle = Bundle.model_validate_json((CASES_DIR / "code_wrong.json").read_text())
    report = review_bundle(bundle, ReviewConfig.from_env(), use_cache=False)
    mismatches = [f for f in report.findings if f.severity == "blocker"]
    assert mismatches
    for finding in mismatches:
        if finding.counterexample is not None:
            assert finding.expected_route != finding.actual_route
            assert finding.evidence
