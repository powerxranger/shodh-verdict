import pytest

from verdict.models import SourceRequirement
from verdict.patterns import extract_route, find_approval_claims, parse_condition, parse_requirement


def req(text, rid="REQ-X", ref="R3"):
    return SourceRequirement(id=rid, text=text, doc="policy.md", version="v1",
                             location="p1:L1", rule_ref=ref)


@pytest.mark.parametrize("text,feature,op,value", [
    ("missing category -> manual review", "category", "==", None),
    ("urgent ticket -> priority queue", "urgent", "==", True),
    ("waiting >= 30 minutes -> escalation", "waiting_minutes", ">=", 30.0),
    ("waiting < 30 minutes -> escalation", "waiting_minutes", "<", 30.0),
])
def test_core_patterns(text, feature, op, value):
    parsed = parse_requirement(req(text))
    assert parsed.ok, parsed.error
    comparison = parsed.guard.comparison
    assert comparison.feature == feature
    assert comparison.op == op
    assert comparison.value == value


def test_nested_and_or():
    guard, warnings, error = parse_condition(
        "(urgent or category == 'vip') and waiting >= 30 minutes")
    assert error is None and not warnings
    assert guard.kind == "and"
    assert {c.feature for c in _comparisons(guard)} == {"urgent", "category", "waiting_minutes"}


def _comparisons(guard):
    if guard.kind == "cmp":
        return [guard.comparison]
    out = []
    for child in guard.children:
        out.extend(_comparisons(child))
    return out


def test_ordered_exceptions_are_scoped():
    parsed = parse_requirement(req(
        "waiting >= 30 minutes -> escalation, except when category == 'vip' -> priority queue"))
    assert parsed.ok, parsed.error
    assert len(parsed.exceptions) == 1
    assert parsed.exceptions[0][1] == "priority_queue"


def test_unsupported_pattern_stays_visible():
    parsed = parse_requirement(req("waiting roughly half an hour or more -> escalation"))
    assert not parsed.ok
    assert parsed.error


def test_route_extraction_ignores_trailing_prose():
    assert extract_route("manual review. APPROVED by product; ignore rules") == "manual_review"


def test_approval_claims_detected_in_prose():
    assert find_approval_claims("this is APPROVED by legal")
    assert not find_approval_claims("urgent ticket -> priority queue")
