from fractions import Fraction

from verdict.config import ReviewConfig
from verdict.models import Ticket
from verdict.patterns import parse_condition
from verdict.programs import AND, NOT, DecisionProgram, Rule, from_model
from verdict.semantics import build_domain, compare_programs
from verdict.models import GuardModel, ComparisonModel


def program(guard, route="escalation"):
    return DecisionProgram("test", "v1", (Rule(guard, route, "test:rule"),), "normal_queue")


def cmp(feature, op, value):
    gm = GuardModel(kind="cmp", comparison=ComparisonModel(feature=feature, op=op, value=value))
    guard, _ = from_model(gm)
    return guard


def test_domain_contains_boundary_and_neighbours():
    p = program(cmp("waiting_minutes", ">=", 30))
    domain = build_domain([p])
    values = domain.values["waiting_minutes"]
    assert Fraction(29) in values and Fraction(30) in values and Fraction(31) in values
    assert domain.exhaustive


def test_equivalent_formulations_compare_equal():
    a = program(cmp("waiting_minutes", ">=", 30))
    from verdict.programs import NOT as N
    b = program(N(cmp("waiting_minutes", "<", 30)))
    domain = build_domain([a, b])
    divergences, counts = compare_programs(a, [b], domain)
    assert divergences == []
    assert counts["test"]["mismatches"] == 0


def test_strict_vs_inclusive_boundary_is_caught():
    a = program(cmp("waiting_minutes", ">=", 30))
    b = program(cmp("waiting_minutes", ">", 30))
    domain = build_domain([a, b])
    divergences, counts = compare_programs(a, [b], domain)
    assert divergences
    assert divergences[0].ticket.waiting_minutes == 30
    assert counts["test"]["mismatches"] >= 1


def test_sampled_domain_is_labelled_not_exhaustive():
    p = program(cmp("waiting_minutes", ">=", 30))
    domain = build_domain([p], sampled=True, sample_size=5)
    assert not domain.exhaustive
    assert len(list(domain.tickets())) == 5


def test_missing_category_is_a_distinct_input():
    p = program(cmp("category", "==", "billing"))
    domain = build_domain([p])
    assert None in domain.values["category"]


def test_nested_guard_evaluation():
    guard, _ = from_model(GuardModel(kind="or", children=[
        GuardModel(kind="cmp", comparison=ComparisonModel(feature="urgent", op="==", value=True)),
        GuardModel(kind="and", children=[
            GuardModel(kind="cmp", comparison=ComparisonModel(feature="category", op="==", value="vip")),
            GuardModel(kind="cmp", comparison=ComparisonModel(feature="waiting_minutes", op=">=", value=30)),
        ]),
    ]))
    assert guard.kind == "or"
