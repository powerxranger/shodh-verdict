"""Stage 1 input contracts.

Every substantive element carries an EvidenceAnchor (artifact, version, location)
and every rule carries a source_ref so omissions are visible rather than silent.
"""

from __future__ import annotations

import textwrap
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import canonical_route

Op = Literal["==", "!=", ">=", ">", "<=", "<"]


class EvidenceAnchor(BaseModel):
    artifact: str
    version: str
    location: str
    excerpt: str | None = None

    def label(self) -> str:
        return f"{self.artifact}@{self.version}:{self.location}"


class ComparisonModel(BaseModel):
    feature: str
    op: Op
    value: Any
    unit: str | None = None


class GuardModel(BaseModel):
    kind: Literal["cmp", "and", "or", "not", "true", "false"]
    comparison: ComparisonModel | None = None
    children: list["GuardModel"] = Field(default_factory=list)


GuardModel.model_rebuild()


class ExceptionModel(BaseModel):
    guard: GuardModel
    route: str
    label: str | None = None


class SourceRequirement(BaseModel):
    """An anchored, versioned written requirement."""

    id: str
    text: str
    doc: str
    version: str
    location: str
    rule_ref: str
    priority: int = 0
    parseable: bool = True


class SpecRule(BaseModel):
    id: str
    source_ref: str | None = None
    guard: GuardModel
    route: str
    exceptions: list[ExceptionModel] = Field(default_factory=list)
    priority: int = 0
    notes: str | None = None


class StructuredSpec(BaseModel):
    version: str
    artifact_id: str = "spec"
    default_route: str = "normal_queue"
    rules: list[SpecRule] = Field(default_factory=list)
    feature_units: dict[str, str] = Field(default_factory=dict)
    rejected_suggestions: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowNode(BaseModel):
    id: str
    kind: Literal["start", "decision", "terminal"]
    version: str = "1"
    condition: GuardModel | None = None
    true_next: str | None = None
    false_next: str | None = None
    destination: str | None = None
    source_ref: str | None = None
    location: str | None = None


class Workflow(BaseModel):
    version: str
    artifact_id: str = "workflow"
    start: str
    nodes: list[WorkflowNode] = Field(default_factory=list)


class PythonSnippet(BaseModel):
    version: str
    artifact_id: str = "code"
    path: str
    function: str
    code: str
    source_ref: str | None = None
    location: str | None = None


class ApprovalRecord(BaseModel):
    """Approval metadata is trusted ONLY at this top level, never in prose."""

    change_id: str
    scope_rule_id: str
    scope_field: str
    proposed_value: Any
    approved: bool
    version: str = "1"
    applies_to: list[str] = Field(default_factory=list)
    decided_by: str | None = None


class Ticket(BaseModel):
    """A concrete input used for counterexamples and evaluation."""

    category: str | None = None
    urgent: bool | None = None
    waiting_minutes: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    id: str
    severity: Literal["blocker", "major", "minor", "info"]
    kind: str
    rule_ref: str | None = None
    artifact: str
    version: str
    location: str
    evidence: list[str] = Field(default_factory=list)
    message: str
    correction: str
    expected_route: str | None = None
    actual_route: str | None = None
    counterexample: Ticket | None = None
    origin: Literal["deterministic", "model", "config"] = "deterministic"

    def canonical(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        if self.counterexample is not None:
            data["counterexample"] = self.counterexample.model_dump(mode="json")
        return data


class CheckResult(BaseModel):
    name: str
    passed: bool
    exhaustive: bool
    partitions: int = 0
    detail: str = ""


class Coverage(BaseModel):
    mode: Literal["exhaustive", "partial", "sampled"]
    supported_scope: str
    reviewed_requirements: list[str] = Field(default_factory=list)
    unreviewed: list[dict[str, str]] = Field(default_factory=list)
    partitions_tested: int = 0
    artifacts_reviewed: list[str] = Field(default_factory=list)


class ModelProvenance(BaseModel):
    client: str
    scenario: str
    request_config: dict[str, Any] = Field(default_factory=dict)
    response_sha256: str | None = None
    attempts: int = 0
    tokens_used: int = 0
    failures: list[str] = Field(default_factory=list)
    real_model: bool = False

    def note(self) -> str:
        return (
            f"{self.client}/{self.scenario} attempts={self.attempts} "
            f"tokens={self.tokens_used} sha={self.response_sha256} "
            f"real_model={self.real_model}"
        )


class ReviewReport(BaseModel):
    status: Literal["PASS", "CHANGES_REQUIRED", "INCOMPLETE"]
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    coverage: Coverage
    check_results: list[CheckResult] = Field(default_factory=list)
    model: ModelProvenance | None = None
    content_hashes: dict[str, str] = Field(default_factory=dict)
    config_signature: str = ""

    def to_json(self) -> str:
        """Machine-readable report (the assessment's required output contract)."""
        return self.model_dump_json(indent=2, exclude_none=False)

    def to_text(self) -> str:
        """Human-readable rendering of the same report for terminal display.

        JSON remains the default and authoritative output; this is a pure view
        over the identical data, with no extra findings or status logic.
        """
        rule = "=" * 76

        def field(label: str, text: str, indent: str = "     ") -> str:
            prefix = f"{indent}{label}"
            return textwrap.TextWrapper(
                width=88, initial_indent=prefix,
                subsequent_indent=" " * len(prefix),
            ).fill(str(text)).rstrip()

        lines: list[str] = [rule, "VERDICT - REVIEW REPORT", rule]
        lines.append(f"  Status : {self.status}")
        lines.append(field("Summary: ", self.summary, indent="  "))
        lines.append("")

        cov = self.coverage
        lines.append("COVERAGE")
        lines.append(f"  Mode         : {cov.mode}")
        lines.append(f"  Partitions   : {cov.partitions_tested}")
        lines.append(f"  Requirements : {', '.join(cov.reviewed_requirements) or 'none'}")
        lines.append(f"  Artifacts    : {', '.join(cov.artifacts_reviewed) or 'none'}")
        lines.append(f"  Unreviewed   : {len(cov.unreviewed)} item(s)")
        for item in cov.unreviewed:
            lines.append(f"                 - {item.get('scope', '?')}: {item.get('reason', '')}")
        lines.append(field("Scope: ", cov.supported_scope, indent="  "))
        lines.append("")

        lines.append("CHECK RESULTS")
        if not self.check_results:
            lines.append("  No checks recorded.")
        for check in self.check_results:
            mark = "PASS" if check.passed else "FAIL"
            mode = "exhaustive" if check.exhaustive else "sampled"
            detail = f" - {check.detail}" if check.detail else ""
            lines.append(f"  [{mark}] {check.name} ({mode}, {check.partitions} partitions){detail}")
        lines.append("")

        if self.model is not None:
            lines.append("MODEL PROVENANCE")
            lines.append(f"  Client       : {self.model.client}/{self.model.scenario}")
            lines.append(f"  Real model   : {'yes' if self.model.real_model else 'no (synthetic)'}")
            lines.append(f"  Attempts     : {self.model.attempts}    Tokens: {self.model.tokens_used}")
            if self.model.response_sha256:
                lines.append(f"  Response SHA : {self.model.response_sha256[:16]}...")
            if self.model.failures:
                for failure in self.model.failures:
                    lines.append(f"  Failure      : {failure}")
            lines.append("")

        lines.append(f"FINDINGS ({len(self.findings)})")
        if not self.findings:
            lines.append("  None. No blocker was established by the deterministic review.")
        for index, finding in enumerate(self.findings, start=1):
            lines.append(f"  {index}. [{finding.severity.upper()}] {finding.kind} "
                         f"(origin: {finding.origin})")
            lines.append(f"     Where   : {finding.artifact}@{finding.version}:{finding.location}")
            if finding.rule_ref:
                lines.append(f"     Rule    : {finding.rule_ref}")
            lines.append(field("Message: ", finding.message))
            lines.append(field("Fix: ", finding.correction))
            for evidence in finding.evidence:
                lines.append(field("Evidence: ", evidence))
            if finding.expected_route or finding.actual_route or finding.counterexample:
                lines.append("     Counterexample:")
                if finding.expected_route or finding.actual_route:
                    lines.append(f"       expected route: {finding.expected_route or 'n/a'}")
                    lines.append(f"       actual route  : {finding.actual_route or 'n/a'}")
                if finding.counterexample is not None:
                    ticket = finding.counterexample
                    lines.append(f"       category={ticket.category!r}, urgent={ticket.urgent!r}, "
                                 f"waiting_minutes={ticket.waiting_minutes!r}")
            lines.append("")

        lines.append(rule)
        lines.append(f"RESULT: {self.status}")
        lines.append(rule)
        return "\n".join(lines)


class Bundle(BaseModel):
    """A complete review input built entirely from synthetic data."""

    id: str
    requirements: list[SourceRequirement] = Field(default_factory=list)
    spec: StructuredSpec
    workflow: Workflow
    snippets: list[PythonSnippet] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    expected_status: str | None = None
    expected_finding_kinds: list[str] = Field(default_factory=list)
    description: str = ""
    model_scenario: str = "valid_clean"
    config: dict[str, Any] = Field(default_factory=dict)


def route_of(raw: str | None) -> str:
    return canonical_route(raw)
