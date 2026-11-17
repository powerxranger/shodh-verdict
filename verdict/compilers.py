"""Compilers from each artifact into the shared DecisionProgram form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .approvals import EffectiveRequirement
from .config import ROUTE_UNKNOWN, canonical_route
from .models import (
    EvidenceAnchor, Finding, SourceRequirement, StructuredSpec, Workflow,
)
from .patterns import parse_requirement
from .programs import (
    AND, NOT, TRUE, DecisionProgram, Guard, Rule, from_model,
)


def _unsupported_finding(req: SourceRequirement, error: str, doc: str,
                         version: str, location: str) -> Finding:
    return Finding(
        id=f"UNSUPPORTED_SOURCE_PATTERN:{req.id}",
        severity="major", kind="UNSUPPORTED_SOURCE_PATTERN", rule_ref=req.rule_ref,
        artifact=doc, version=version, location=location,
        evidence=[f"requirement {req.id}: '{req.text}'"],
        message=f"Requirement {req.id} cannot be compiled: {error}.",
        correction="Rewrite the requirement using the documented supported patterns.",
    )


def compile_requirements(
    effective: list[EffectiveRequirement],
    feature_units: dict[str, str] | None = None,
) -> tuple[DecisionProgram, list[Finding], list[str]]:
    """Compile effective (post-approval) requirements into the oracle program."""
    findings: list[Finding] = []
    unreviewed: list[str] = []
    rules: list[Rule] = []
    default_route = ROUTE_UNKNOWN

    for eff in effective:
        req = eff.as_source()
        parsed = parse_requirement(req, feature_units)
        if not parsed.ok:
            findings.append(_unsupported_finding(
                req, parsed.error or "unknown parse failure", req.doc, req.version, req.location))
            unreviewed.append(f"requirement:{req.id}")
            continue
        anchor = f"{req.doc}@{req.version}:{req.location}"
        for guard, route, label in parsed.exceptions:
            # An exception is scoped to the rule it qualifies, not global.
            scoped = AND(parsed.guard, guard) if parsed.guard is not None else guard
            rules.append(Rule(scoped, route, f"exception:{req.id}:{label}",
                              req.rule_ref, anchor))
        if parsed.is_default:
            default_route = parsed.route or default_route
        elif parsed.guard is not None:
            rules.append(Rule(parsed.guard, parsed.route or ROUTE_UNKNOWN,
                              f"requirement:{req.id}", req.rule_ref, anchor))

    rules.sort(key=lambda r: next(
        (e.priority for e in effective if e.rule_ref == r.source_ref), 99))
    program = DecisionProgram(
        origin="requirements", version=effective[0].requirement.version if effective else "n/a",
        rules=tuple(rules), default_route=default_route,
    )
    return program, findings, unreviewed


def compile_spec(spec: StructuredSpec) -> tuple[DecisionProgram, list[Finding], list[str]]:
    findings: list[Finding] = []
    unreviewed: list[str] = []
    rules: list[Rule] = []
    for sr in sorted(spec.rules, key=lambda r: r.priority):
        guard, warnings = from_model(sr.guard, spec.feature_units)
        anchor = f"{spec.artifact_id}@{spec.version}:rule:{sr.id}"
        for warning in warnings:
            findings.append(Finding(
                id=f"SPEC_UNIT_WARNING:{sr.id}", severity="major", kind="UNIT_AMBIGUITY",
                rule_ref=sr.source_ref or sr.id, artifact=spec.artifact_id, version=spec.version,
                location=f"rule:{sr.id}", evidence=[warning],
                message=f"Spec rule {sr.id}: {warning}.",
                correction="Declare an explicit, consistent time unit for the comparison.",
            ))
        for exc in sr.exceptions:
            eguard, _ = from_model(exc.guard, spec.feature_units)
            scoped = AND(guard, eguard)
            rules.append(Rule(scoped, canonical_route(exc.route),
                              f"exception:{sr.id}:{exc.label or ''}", sr.source_ref, anchor))
        rules.append(Rule(guard, canonical_route(sr.route), f"spec:{sr.id}",
                          sr.source_ref, anchor))
    program = DecisionProgram(
        origin="spec", version=spec.version, rules=tuple(rules),
        default_route=canonical_route(spec.default_route),
    )
    return program, findings, unreviewed


@dataclass
class WorkflowStats:
    visited: set[str]
    cycles: list[str]
    dangling: list[str]
    missing_destination: list[str]


def compile_workflow(wf: Workflow, feature_units: dict[str, str] | None = None
                     ) -> tuple[DecisionProgram, list[Finding], list[str], WorkflowStats]:
    findings: list[Finding] = []
    unreviewed: list[str] = []
    nodes = {n.id: n for n in wf.nodes}
    stats = WorkflowStats(set(), [], [], [])
    paths: list[tuple[Guard, str, str]] = []

    default_nodes = [n for n in wf.nodes if n.kind == "terminal" and n.condition is None]

    def walk(node_id: str, path: Guard, stack: tuple[str, ...]) -> None:
        if node_id in stack:
            stats.cycles.append(" -> ".join((*stack, node_id)))
            return
        node = nodes.get(node_id)
        if node is None:
            stats.dangling.append(node_id)
            return
        stats.visited.add(node_id)
        anchor = f"{wf.artifact_id}@{wf.version}:node:{node_id}"

        if node.kind == "terminal":
            if not node.destination:
                stats.missing_destination.append(node_id)
                return
            paths.append((path, canonical_route(node.destination), anchor))
            return

        if node.condition is None:
            if node.true_next:
                walk(node.true_next, path, (*stack, node_id))
            else:
                stats.dangling.append(node_id)
            return

        guard, warnings = from_model(node.condition, feature_units)
        for warning in warnings:
            findings.append(Finding(
                id=f"WORKFLOW_UNIT_WARNING:{node_id}", severity="major", kind="UNIT_AMBIGUITY",
                rule_ref=node.source_ref or node_id, artifact=wf.artifact_id, version=wf.version,
                location=f"node:{node_id}", evidence=[warning],
                message=f"Workflow node {node_id}: {warning}.",
                correction="Declare an explicit, consistent time unit.",
            ))
        if node.true_next:
            walk(node.true_next, AND(path, guard), (*stack, node_id))
        if node.false_next:
            walk(node.false_next, AND(path, NOT(guard)), (*stack, node_id))
        if not node.true_next and not node.false_next:
            stats.dangling.append(node_id)

    walk(wf.start, TRUE, ())

    for node_id in stats.cycles:
        findings.append(Finding(
            id=f"WORKFLOW_CYCLE:{node_id}", severity="blocker", kind="WORKFLOW_CYCLE",
            rule_ref=None, artifact=wf.artifact_id, version=wf.version,
            location=f"path:{node_id}", evidence=[node_id],
            message=f"Workflow contains a cycle: {node_id}.",
            correction="Remove the cycle; decision workflows must be acyclic.",
        ))
        unreviewed.append(f"workflow-path:{node_id}")
    for node_id in stats.dangling:
        findings.append(Finding(
            id=f"WORKFLOW_DANGLING:{node_id}", severity="blocker", kind="MISSING_BRANCH",
            rule_ref=None, artifact=wf.artifact_id, version=wf.version,
            location=f"node:{node_id}", evidence=[f"missing target '{node_id}'"],
            message=f"Branch points to missing node '{node_id}'.",
            correction="Add the target node or redirect the branch.",
        ))
        unreviewed.append(f"workflow-node:{node_id}")
    for node_id in stats.missing_destination:
        findings.append(Finding(
            id=f"WORKFLOW_NO_DESTINATION:{node_id}", severity="blocker", kind="MISSING_DESTINATION",
            rule_ref=None, artifact=wf.artifact_id, version=wf.version,
            location=f"node:{node_id}", evidence=["terminal without destination"],
            message=f"Terminal node {node_id} has no destination route.",
            correction="Assign a destination route to the terminal node.",
        ))
        unreviewed.append(f"workflow-node:{node_id}")
    for node in wf.nodes:
        if node.id not in stats.visited:
            findings.append(Finding(
                id=f"WORKFLOW_UNREACHABLE:{node.id}", severity="minor", kind="UNREACHABLE_NODE",
                rule_ref=node.source_ref, artifact=wf.artifact_id, version=wf.version,
                location=f"node:{node.id}", evidence=["not reachable from start"],
                message=f"Workflow node {node.id} is unreachable.",
                correction="Remove the node or connect a reachable branch to it.",
            ))

    rules = tuple(Rule(g, r, "workflow-path", None, loc) for g, r, loc in paths)
    default_route = ROUTE_UNKNOWN
    for guard, route, _ in paths:
        if guard.kind == "true":
            default_route = route
    program = DecisionProgram(
        origin="workflow", version=wf.version, rules=rules, default_route=default_route,
    )
    return program, findings, unreviewed, stats
