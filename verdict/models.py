"""Stage 1 input contracts.

Every substantive element carries an EvidenceAnchor (artifact, version, location)
and every rule carries a source_ref so omissions are visible rather than silent.
"""

from __future__ import annotations

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
        return self.model_dump_json(indent=2, exclude_none=False)


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
