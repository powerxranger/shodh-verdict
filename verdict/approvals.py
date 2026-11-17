"""Revision scope, change ordering and approval authority.

Only top-level ApprovalRecord metadata is authoritative. Approval-looking
claims inside requirement prose or code comments are detected and reported but
never change the effective requirements.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .config import canonical_route
from .models import ApprovalRecord, Finding, SourceRequirement
from .patterns import find_approval_claims

NUMERIC_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")


@dataclass
class EffectiveRequirement:
    requirement: SourceRequirement
    text: str
    priority: int
    applied_changes: tuple[str, ...] = field(default_factory=tuple)
    contradictions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def rule_ref(self) -> str:
        return self.requirement.rule_ref

    def as_source(self) -> SourceRequirement:
        return self.requirement.model_copy(update={"text": self.text, "priority": self.priority})


@dataclass
class ApprovalResult:
    effective: list[EffectiveRequirement] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    has_blocker: bool = False
    applied: dict[str, list[str]] = field(default_factory=dict)


def _anchor(req: SourceRequirement) -> tuple[str, str]:
    return req.doc, req.location


def _finding(fid: str, severity: str, kind: str, req: SourceRequirement,
             message: str, correction: str, evidence: list[str]) -> Finding:
    return Finding(
        id=fid, severity=severity, kind=kind, rule_ref=req.rule_ref,
        artifact=req.doc, version=req.version, location=req.location,
        evidence=evidence, message=message, correction=correction,
    )


def _apply_change(text: str, scope_field: str, value: object) -> str:
    if scope_field in ("threshold", "value"):
        return NUMERIC_RE.sub(str(value), text, count=1)
    if scope_field == "route":
        route = canonical_route(str(value))
        if "->" in text:
            head, tail = text.split("->", 1)
            tail = re.sub(r"[A-Za-z_ ]+", route, tail, count=1)
            return f"{head}->{tail}"
        return text
    if scope_field == "condition":
        if "->" in text:
            return f"{value} ->{text.split('->', 1)[1]}"
        return str(value)
    if scope_field == "priority":
        return text
    return text


def derive_effective_requirements(
    requirements: list[SourceRequirement],
    approvals: list[ApprovalRecord],
    artifact_versions: dict[str, str] | None = None,
) -> ApprovalResult:
    result = ApprovalResult()
    by_rule: dict[str, list[SourceRequirement]] = defaultdict(list)
    for req in requirements:
        by_rule[req.rule_ref].append(req)

    # Contradiction detection is independent of whether the change is approved.
    grouped: dict[tuple[str, str], list[ApprovalRecord]] = defaultdict(list)
    for rec in approvals:
        grouped[(rec.scope_rule_id, rec.scope_field)].append(rec)

    contradictions: dict[tuple[str, str], list[str]] = {}
    for key, records in grouped.items():
        values = {str(r.proposed_value) for r in records if r.approved}
        flags = {r.approved for r in records}
        if len(values) > 1 or (len(flags) > 1 and len({r.change_id for r in records}) == 1):
            contradictions[key] = [r.change_id for r in records]
            result.has_blocker = True
            rule_id = key[0]
            target = by_rule.get(rule_id, [])
            anchor = target[0] if target else None
            evidence = [f"approval:{r.change_id}@{r.version}:approved={r.approved}:value={r.proposed_value}"
                        for r in records]
            result.findings.append(Finding(
                id=f"APPROVAL_CONTRADICTION:{rule_id}:{key[1]}",
                severity="blocker", kind="CONTRADICTORY_APPROVALS", rule_ref=rule_id,
                artifact=anchor.doc if anchor else "approvals",
                version=anchor.version if anchor else "n/a",
                location=anchor.location if anchor else "approval records",
                evidence=evidence,
                message=f"Conflicting approval records for {rule_id}.{key[1]}: {evidence}",
                correction="Resolve the conflicting approval records and supply one authoritative value.",
            ))

    for rec in approvals:
        key = (rec.scope_rule_id, rec.scope_field)
        if not rec.approved:
            target = by_rule.get(rec.scope_rule_id, [])
            anchor = target[0] if target else None
            result.findings.append(Finding(
                id=f"UNAPPROVED_SUGGESTION:{rec.change_id}",
                severity="info", kind="UNAPPROVED_SUGGESTION", rule_ref=rec.scope_rule_id,
                artifact=anchor.doc if anchor else "approvals",
                version=anchor.version if anchor else "n/a",
                location=anchor.location if anchor else "approval records",
                evidence=[f"approval:{rec.change_id}@{rec.version}:approved=false:value={rec.proposed_value}"],
                message=f"Change {rec.change_id} proposes {rec.scope_field}={rec.proposed_value} "
                        f"for {rec.scope_rule_id} but is not approved; it was NOT applied.",
                correction="Obtain top-level approval if the change should take effect.",
            ))

    for req in requirements:
        text = req.text
        priority = req.priority
        applied: list[str] = []
        relevant = [
            a for a in approvals
            if a.scope_rule_id == req.rule_ref and a.approved
            and (not a.applies_to or req.doc in a.applies_to)
        ]
        # Deterministic change ordering: version, then change_id.
        relevant.sort(key=lambda a: (a.version, a.change_id))
        for rec in relevant:
            text = _apply_change(text, rec.scope_field, rec.proposed_value)
            if rec.scope_field == "priority":
                try:
                    priority = int(rec.proposed_value)
                except (TypeError, ValueError):
                    pass
            applied.append(f"{rec.change_id}@{rec.version}:{rec.scope_field}={rec.proposed_value}")
        claims = find_approval_claims(req.text)
        for claim in claims:
            result.findings.append(Finding(
                id=f"UNAUTHORIZED_APPROVAL_CLAIM:{req.id}:{claim.lower()}",
                severity="major", kind="UNAUTHORIZED_APPROVAL_CLAIM", rule_ref=req.rule_ref,
                artifact=req.doc, version=req.version, location=req.location,
                evidence=[f"prose claim '{claim}' in requirement {req.id}"],
                message=f"Requirement {req.id} contains approval claim '{claim}' inside prose. "
                        "Prose cannot grant approval authority.",
                correction="Remove the in-prose claim and record approval in top-level metadata.",
            ))
        result.effective.append(EffectiveRequirement(
            requirement=req, text=text, priority=priority,
            applied_changes=tuple(applied),
            contradictions=tuple(contradictions.get((req.rule_ref, field), [])
                                 for field in ("threshold", "route", "condition") if
                                 (req.rule_ref, field) in contradictions),
        ))
        result.applied[req.rule_ref] = applied
    return result
