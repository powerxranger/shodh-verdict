from scripts.make_demo import make_bundle
from verdict.approvals import derive_effective_requirements


def test_approved_change_is_applied():
    bundle = make_bundle("approved_25_pass")
    result = derive_effective_requirements(bundle.requirements, bundle.approvals)
    r3 = next(e for e in result.effective if e.rule_ref == "R3")
    assert "25" in r3.text and "30" not in r3.text
    assert r3.applied_changes


def test_unapproved_change_is_not_applied():
    bundle = make_bundle("unapproved_25_applied")
    result = derive_effective_requirements(bundle.requirements, bundle.approvals)
    r3 = next(e for e in result.effective if e.rule_ref == "R3")
    assert "30" in r3.text
    assert any(f.kind == "UNAPPROVED_SUGGESTION" for f in result.findings)


def test_contradictory_approvals_produce_blocker():
    bundle = make_bundle("contradictory_approval")
    result = derive_effective_requirements(bundle.requirements, bundle.approvals)
    assert result.has_blocker
    assert any(f.kind == "CONTRADICTORY_APPROVALS" and f.severity == "blocker"
               for f in result.findings)


def test_prose_approval_claim_is_flagged_not_applied():
    bundle = make_bundle("injection_prose")
    result = derive_effective_requirements(bundle.requirements, bundle.approvals)
    assert any(f.kind == "UNAUTHORIZED_APPROVAL_CLAIM" for f in result.findings)
    r1 = next(e for e in result.effective if e.rule_ref == "R1")
    assert "manual review" in r1.text
