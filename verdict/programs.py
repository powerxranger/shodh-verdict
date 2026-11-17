"""Internal, immutable decision-program representation.

Requirements, specification, workflow graph and linked Python all compile to
this single form so that semantic equivalence can be decided exhaustively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .config import (
    BASE_TIME_UNIT,
    MISSING,
    ROUTE_UNKNOWN,
    TIME_FEATURES,
    UNIT_TO_MINUTES,
)
from .models import GuardModel, Ticket


@dataclass(frozen=True)
class Comparison:
    feature: str
    op: str
    value: Any
    unit: str | None = None
    raw_value: Any = None


@dataclass(frozen=True)
class Guard:
    kind: str
    comparison: Comparison | None = None
    children: tuple["Guard", ...] = ()


@dataclass(frozen=True)
class Rule:
    guard: Guard
    route: str
    label: str
    source_ref: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class DecisionProgram:
    origin: str
    version: str
    rules: tuple[Rule, ...]
    default_route: str = ROUTE_UNKNOWN


TRUE = Guard("true")
FALSE = Guard("false")


def cmp(feature: str, op: str, value: Any, unit: str | None = None,
        raw_value: Any = None) -> Guard:
    return Guard("cmp", Comparison(feature, op, value, unit, raw_value))


def AND(*children: Guard) -> Guard:
    flat: list[Guard] = []
    for c in children:
        if c.kind == "true":
            continue
        if c.kind == "false":
            return FALSE
        if c.kind == "and":
            flat.extend(c.children)
        else:
            flat.append(c)
    if not flat:
        return TRUE
    if len(flat) == 1:
        return flat[0]
    return Guard("and", children=tuple(flat))


def OR(*children: Guard) -> Guard:
    flat: list[Guard] = []
    for c in children:
        if c.kind == "false":
            continue
        if c.kind == "true":
            return TRUE
        if c.kind == "or":
            flat.extend(c.children)
        else:
            flat.append(c)
    if not flat:
        return FALSE
    if len(flat) == 1:
        return flat[0]
    return Guard("or", children=tuple(flat))


def NOT(child: Guard) -> Guard:
    if child.kind == "true":
        return FALSE
    if child.kind == "false":
        return TRUE
    if child.kind == "not":
        return child.children[0]
    return Guard("not", children=(child,))


def missing_guard(feature: str) -> Guard:
    return cmp(feature, "==", None)


# ---------------------------------------------------------------------------
# Unit handling
# ---------------------------------------------------------------------------

def to_base_units(value: Any, feature: str, unit: str | None) -> tuple[Any, str | None]:
    """Normalise a comparison value to the feature's base unit.

    Returns (normalised_value, warning) where warning is non-None when the unit
    is missing or unknown for a time feature. Such warnings remain visible.
    """
    if feature not in TIME_FEATURES:
        return value, None
    if unit is None:
        return value, f"time feature '{feature}' compared without a declared unit"
    key = str(unit).strip().lower()
    factor = UNIT_TO_MINUTES.get(key)
    if factor is None:
        return value, f"unknown time unit '{unit}' for feature '{feature}'"
    try:
        return float(value) * factor, None
    except (TypeError, ValueError):
        return value, f"non-numeric value '{value}' for time feature '{feature}'"


def from_model(model: GuardModel, feature_units: dict[str, str] | None = None
               ) -> tuple[Guard, list[str]]:
    """Convert a serialisable GuardModel into an internal Guard."""
    warnings: list[str] = []
    units = feature_units or {}

    def walk(node: GuardModel) -> Guard:
        if node.kind == "cmp":
            assert node.comparison is not None
            c = node.comparison
            unit = c.unit or units.get(c.feature)
            norm, warning = to_base_units(c.value, c.feature, unit)
            if warning:
                warnings.append(warning)
            return cmp(c.feature, c.op, norm, unit, c.value)
        if node.kind == "and":
            return AND(*(walk(ch) for ch in node.children))
        if node.kind == "or":
            return OR(*(walk(ch) for ch in node.children))
        if node.kind == "not":
            return NOT(walk(node.children[0]))
        return TRUE if node.kind == "true" else FALSE

    return walk(model), warnings


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _feature_value(ticket: Ticket, feature: str) -> Any:
    if hasattr(ticket, feature):
        return getattr(ticket, feature)
    return ticket.extra.get(feature)


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def eval_comparison(c: Comparison, ticket: Ticket) -> bool:
    actual = _feature_value(ticket, c.feature)
    expected = c.value

    if expected is None:
        is_missing = actual is None or actual == MISSING
        return is_missing if c.op == "==" else (not is_missing if c.op == "!=" else False)

    if actual is None or actual == MISSING:
        return False

    a, e = _norm(actual), _norm(expected)
    try:
        if c.op == "==":
            return a == e
        if c.op == "!=":
            return a != e
        if c.op == ">=":
            return a >= e
        if c.op == ">":
            return a > e
        if c.op == "<=":
            return a <= e
        if c.op == "<":
            return a < e
    except TypeError:
        return False
    return False


def eval_guard(guard: Guard, ticket: Ticket) -> bool:
    if guard.kind == "true":
        return True
    if guard.kind == "false":
        return False
    if guard.kind == "cmp":
        assert guard.comparison is not None
        return eval_comparison(guard.comparison, ticket)
    if guard.kind == "not":
        return not eval_guard(guard.children[0], ticket)
    if guard.kind == "and":
        return all(eval_guard(ch, ticket) for ch in guard.children)
    if guard.kind == "or":
        return any(eval_guard(ch, ticket) for ch in guard.children)
    raise ValueError(f"unknown guard kind: {guard.kind}")


def eval_program(program: DecisionProgram, ticket: Ticket) -> str:
    for rule in program.rules:
        if eval_guard(rule.guard, ticket):
            return rule.route
    return program.default_route


# ---------------------------------------------------------------------------
# Introspection used by the exhaustive domain builder
# ---------------------------------------------------------------------------

def iter_comparisons(guard: Guard) -> Iterable[Comparison]:
    if guard.kind == "cmp" and guard.comparison is not None:
        yield guard.comparison
    for ch in guard.children:
        yield from iter_comparisons(ch)


def program_comparisons(program: DecisionProgram) -> list[Comparison]:
    seen: dict[tuple, Comparison] = {}
    for rule in program.rules:
        for c in iter_comparisons(rule.guard):
            seen[(c.feature, c.op, str(c.value))] = c
    return list(seen.values())


def features_of(program: DecisionProgram) -> set[str]:
    return {c.feature for c in program_comparisons(program)}


def numeric_boundaries(program: DecisionProgram) -> dict[str, set[Any]]:
    bounds: dict[str, set[Any]] = {}
    for c in program_comparisons(program):
        if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
            bounds.setdefault(c.feature, set()).add(c.value)
    return bounds


def categorical_constants(program: DecisionProgram) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for c in program_comparisons(program):
        if isinstance(c.value, str):
            values.setdefault(c.feature, set()).add(_norm(c.value))
    return values


def program_label(program: DecisionProgram) -> str:
    return f"{program.origin}@{program.version}"
