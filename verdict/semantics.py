"""Exhaustive boundary-partition equivalence over the supported domain.

Key property: for the supported guard language, a guard's truth value can only
change at a comparison boundary or between adjacent boundaries. Therefore a
finite domain containing, for each numeric feature, every boundary, a point in
each open interval, and points outside the extremes, plus every categorical
constant, MISSING and an UNLISTED sentinel, is *complete*. Agreement on that
domain is genuine behavioural equivalence, not sampling.

Ablation mode replaces this with naive random sampling to demonstrate the
mechanism's contribution.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterable

from .config import FEATURE_CATEGORY, FEATURE_URGENT, FEATURE_WAITING
from .models import Ticket
from .programs import (
    DecisionProgram, Rule, eval_guard, eval_program, features_of,
    numeric_boundaries, categorical_constants,
)

UNLISTED = "__UNLISTED_CATEGORY__"


@dataclass
class Domain:
    values: dict[str, tuple[Any, ...]]
    exhaustive: bool = True
    sample_size: int | None = None
    seed: int = 17

    @property
    def size(self) -> int:
        # A sampled domain tests `sample_size` inputs, not the whole product;
        # reporting the product there would overstate actual coverage.
        if not self.exhaustive:
            return self.sample_size or 1
        n = 1
        for vals in self.values.values():
            n *= len(vals)
        return n

    def tickets(self) -> Iterable[Ticket]:
        features = list(self.values)
        if self.exhaustive:
            combos: Iterable[tuple] = itertools.product(*(self.values[f] for f in features))
        else:
            rng = random.Random(self.seed)
            combos = (tuple(rng.choice(self.values[f]) for f in features)
                      for _ in range(self.sample_size or 1))
        for combo in combos:
            kwargs: dict[str, Any] = {}
            extra: dict[str, Any] = {}
            for feature, raw in zip(features, combo):
                value = _render(raw)
                if feature in Ticket.model_fields:
                    kwargs[feature] = value
                else:
                    extra[feature] = value
            if extra:
                kwargs["extra"] = extra
            yield Ticket(**kwargs)


def _render(value: Any) -> Any:
    if isinstance(value, Fraction):
        return int(value) if value.denominator == 1 else float(value)
    if value == UNLISTED:
        return "unlisted_category_value"
    return value


def _fraction(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    return Fraction(str(value))


def build_domain(programs: list[DecisionProgram], *, sampled: bool = False,
                 sample_size: int = 40) -> Domain:
    numeric: dict[str, set[Fraction]] = {}
    categorical: dict[str, set[str]] = {}
    all_features: set[str] = set()

    for program in programs:
        all_features |= features_of(program)
        for feature, values in numeric_boundaries(program).items():
            numeric.setdefault(feature, set()).update(_fraction(v) for v in values)
        for feature, values in categorical_constants(program).items():
            categorical.setdefault(feature, set()).update(values)

    # Ensure the three declared features are always exercised, including MISSING.
    all_features |= {FEATURE_CATEGORY, FEATURE_URGENT, FEATURE_WAITING}

    values: dict[str, tuple[Any, ...]] = {}
    for feature in sorted(all_features):
        if feature in numeric:
            points = sorted(numeric[feature])
            reps: list[Any] = [points[0] - 1]
            for p in points:
                reps.append(p)
            for a, b in zip(points, points[1:]):
                reps.append((a + b) / 2)
            reps.append(points[-1] + 1)
            values[feature] = tuple(dict.fromkeys(reps))
        elif feature == FEATURE_URGENT:
            values[feature] = (True, False, None)
        else:
            consts = sorted(categorical.get(feature, set()))
            if not consts:
                consts = ["general_inquiry"]
            values[feature] = tuple([*consts, UNLISTED, None])

    return Domain(values=values, exhaustive=not sampled,
                  sample_size=sample_size if sampled else None)


@dataclass
class Divergence:
    origin: str
    expected: str
    actual: str
    ticket: Ticket
    oracle_rules: list[str] = field(default_factory=list)
    other_rules: list[str] = field(default_factory=list)
    partitions_total: int = 0
    mismatches_total: int = 0

    def summary(self) -> str:
        t = self.ticket
        return (
            f"ticket(category={t.category!r}, urgent={t.urgent!r}, "
            f"waiting_minutes={t.waiting_minutes!r}) expected={self.expected} "
            f"actual={self.actual}"
        )


def _matched_labels(program: DecisionProgram, ticket: Ticket) -> list[str]:
    out = []
    for rule in program.rules:
        if eval_guard(rule.guard, ticket):
            out.append(rule.label)
            break
    return out


def compare_programs(
    oracle: DecisionProgram,
    others: list[DecisionProgram],
    domain: Domain,
    max_examples: int = 3,
) -> tuple[list[Divergence], dict[str, dict[str, int]]]:
    """Compare each other program against the oracle over the whole domain."""
    divergences: list[Divergence] = []
    counts: dict[str, dict[str, int]] = {
        p.origin: {"mismatches": 0, "partitions": 0} for p in others
    }
    per_origin: dict[str, set[tuple[str, str]]] = {p.origin: set() for p in others}

    for ticket in domain.tickets():
        expected = eval_program(oracle, ticket)
        for other in others:
            counts[other.origin]["partitions"] += 1
            actual = eval_program(other, ticket)
            if actual == expected:
                continue
            counts[other.origin]["mismatches"] += 1
            key = (expected, actual)
            if key in per_origin[other.origin] or len(per_origin[other.origin]) >= max_examples:
                continue
            per_origin[other.origin].add(key)
            divergences.append(Divergence(
                origin=other.origin,
                expected=expected,
                actual=actual,
                ticket=ticket,
                oracle_rules=_matched_labels(oracle, ticket),
                other_rules=_matched_labels(other, ticket),
                partitions_total=domain.size,
                mismatches_total=counts[other.origin]["mismatches"],
            ))
    return divergences, counts


def pairwise_compare(programs: list[DecisionProgram], domain: Domain
                     ) -> list[tuple[str, str, Ticket, str, str]]:
    """Compare non-oracle artifacts to each other for cross-artifact drift."""
    out: list[tuple[str, str, Ticket, str, str]] = []
    seen = set()
    for a, b in itertools.combinations(programs, 2):
        for ticket in domain.tickets():
            ra, rb = eval_program(a, ticket), eval_program(b, ticket)
            if ra != rb and (a.origin, b.origin) not in seen:
                out.append((a.origin, b.origin, ticket, ra, rb))
                seen.add((a.origin, b.origin))
                break
    return out
