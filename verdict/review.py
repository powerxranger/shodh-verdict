"""Stage 2 deterministic semantic review and report construction."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field

from .approvals import ApprovalResult, derive_effective_requirements
from .cache import bundle_hashes
from .compilers import compile_requirements, compile_spec, compile_workflow
from .config import ReviewConfig, ROUTE_UNKNOWN, UNIT_TO_MINUTES, canonical_route
from .models import (
    Bundle, CheckResult, Coverage, Finding, PythonSnippet, ReviewReport, Ticket,
)
from .patterns import find_approval_claims
from .programs import DecisionProgram, Rule, eval_guard, eval_program, program_comparisons
from .python_subset import inspect_snippet
from .semantics import (
    Divergence, build_domain, compare_programs, pairwise_compare,
)


@dataclass
class ReviewContext:
    bundle: Bundle
    config: ReviewConfig
    approvals: ApprovalResult
    programs: dict[str, DecisionProgram]
    findings: list[Finding] = field(default_factory=list)
    unreviewed: list[str] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    check_results: list[CheckResult] = field(default_factory=list)
    domain_size: int = 0
    coverage_mode: str = "exhaustive"
    hashes: dict[str, str] = field(default_factory=dict)
    known_refs: set[str] = field(default_factory=set)
    known_anchors: set[str] = field(default_factory=set)
    model_required: bool = False
    oracle_incomplete: bool = False


def _anchor_set(bundle: Bundle) -> set[str]:
    out = set()
    for r in bundle.requirements:
        out.add(f"{r.doc}@{r.version}:{r.location}")
    out.add(f"{bundle.spec.artifact_id}@{bundle.spec.version}:spec")
    out.add(f"{bundle.workflow.artifact_id}@{bundle.workflow.version}:workflow")
    for s in bundle.snippets:
        out.add(f"{s.artifact_id}@{s.version}:{s.location or s.path}")
    return out


def syntax_check(snippet: PythonSnippet) -> tuple[bool, str]:
    """Separate syntax checking from AST inspection and execution."""
    try:
        compile(snippet.code, snippet.path, "exec")
        return True, ""
    except SyntaxError as exc:
        return False, f"{type(exc).__name__}: {exc.msg} at line {exc.lineno}"


def execute_code(snippet: PythonSnippet, ticket: Ticket) -> tuple[str | None, str]:
    """Opt-in execution in a bounded subprocess. Not used by default."""
    args = ", ".join(
        f"{k}={v!r}" for k, v in {
            "category": ticket.category, "urgent": ticket.urgent,
            "waiting_minutes": ticket.waiting_minutes,
        }.items() if k in snippet.code
    )
    script = f"{snippet.code}\nprint({snippet.function}({args}))\n"
    try:
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=2,
        )
    except subprocess.TimeoutExpired:
        return None, "execution timed out"
    if result.returncode != 0:
        return None, result.stderr.strip()[:300]
    return canonical_route(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""), ""


def _matched_rules(program: DecisionProgram, ticket: Ticket) -> list[Rule]:
    return [r for r in program.rules if eval_guard(r.guard, ticket)]


def _numeric_values(rules: list[Rule]) -> set[float]:
    out = set()
    for rule in rules:
        for c in program_comparisons(DecisionProgram(rule.label, "x", (rule,))):
            if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                out.add(float(c.value))
    return out


def classify_divergence(d: Divergence, oracle: DecisionProgram,
                        other: DecisionProgram) -> str:
    o_rules = _matched_rules(oracle, d.ticket)
    a_rules = _matched_rules(other, d.ticket)
    o_nums, a_nums = _numeric_values(o_rules), _numeric_values(a_rules)
    if o_nums != a_nums:
        return "CHANGED_THRESHOLD"
    o_labels = [r.label for r in o_rules]
    a_labels = [r.label for r in a_rules]
    if o_labels and a_labels and o_labels != a_labels:
        return "INCORRECT_PRECEDENCE"
    if not a_rules:
        return "MISSING_BRANCH"
    return "BEHAVIORAL_MISMATCH"


def _divergence_finding(d: Divergence, oracle: DecisionProgram,
                        other: DecisionProgram, kind: str,
                        oracle_incomplete: bool = False) -> Finding:
    evidence = [f"{d.ticket.category=}", f"{d.ticket.urgent=}",
                f"{d.ticket.waiting_minutes=}"]
    evidence += [f"expected rule: {x}" for x in d.oracle_rules]
    evidence += [f"observed rule: {x}" for x in d.other_rules]
    evidence.append(f"{d.mismatches_total}/{d.partitions_total} partitions disagree")
    return Finding(
        id=f"SEMANTIC_MISMATCH:{other.origin}:{kind}:{d.expected}->{d.actual}",
        severity="major" if oracle_incomplete else "blocker", kind=kind,
        rule_ref=d.oracle_rules[0] if d.oracle_rules else None,
        artifact=other.origin, version=other.version, location="compiled decision paths",
        evidence=evidence,
        message=f"{other.origin} routes {d.summary()}; expected '{d.expected}'.",
        correction=f"Align {other.origin} with the effective requirement so the ticket routes "
                   f"to '{d.expected}' instead of '{d.actual}'.",
        expected_route=d.expected, actual_route=d.actual, counterexample=d.ticket,
    )


def _source_coverage(bundle: Bundle, findings: list[Finding]) -> None:
    spec_refs = {r.source_ref for r in bundle.spec.rules if r.source_ref}
    for req in bundle.requirements:
        if req.text.strip().lower().startswith(("otherwise", "else", "all remaining")):
            continue
        if req.rule_ref not in spec_refs:
            findings.append(Finding(
                id=f"OMITTED_REQUIREMENT:{req.rule_ref}", severity="blocker",
                kind="OMITTED_REQUIREMENT", rule_ref=req.rule_ref, artifact=req.doc,
                version=req.version, location=req.location,
                evidence=[f"requirement {req.id} -> {req.rule_ref}",
                          "no spec rule declares this source_ref"],
                message=f"Requirement {req.rule_ref} is absent from the specification.",
                correction=f"Add a spec rule with source_ref='{req.rule_ref}'.",
            ))
    for sr in bundle.spec.rules:
        if not sr.source_ref:
            findings.append(Finding(
                id=f"ORPHAN_SPEC_RULE:{sr.id}", severity="major", kind="MISSING_SOURCE_REFERENCE",
                rule_ref=sr.id, artifact=bundle.spec.artifact_id, version=bundle.spec.version,
                location=f"rule:{sr.id}", evidence=["rule has no source_ref"],
                message=f"Spec rule {sr.id} has no source reference.",
                correction="Attach the anchored source requirement id to this rule.",
            ))


def _unit_consistency(bundle: Bundle, findings: list[Finding]) -> None:
    for req in bundle.requirements:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
                          req.text.lower())
        if not match:
            continue
        value = float(match.group(1))
        unit = match.group(2)
        base = "seconds" if unit.startswith("sec") else (
            "minutes" if unit.startswith("min") else "hours")
        req_minutes = value * UNIT_TO_MINUTES.get(base, 1.0)
        for rule in bundle.spec.rules:
            comp = rule.guard.comparison
            if not comp or comp.feature != "waiting_minutes" or not isinstance(comp.value, (int, float)):
                continue
            declared_unit = bundle.spec.feature_units.get("waiting_minutes")
            if comp.unit and declared_unit and comp.unit.lower() != str(declared_unit).lower():
                findings.append(Finding(
                    id=f"UNIT_MISMATCH:{req.id}:{rule.id}:declaration", severity="blocker",
                    kind="UNIT_MISMATCH", rule_ref=req.rule_ref, artifact=bundle.spec.artifact_id,
                    version=bundle.spec.version, location=f"rule:{rule.id}",
                    evidence=[f"rule declares '{comp.unit}'",
                              f"spec.feature_units declares '{declared_unit}'"],
                    message=f"Spec rule {rule.id} declares '{comp.unit}' while the spec's "
                            f"feature_units declares '{declared_unit}'.",
                    correction="Use one consistent declared unit across all artifacts.",
                ))
            spec_unit = (comp.unit or declared_unit or "minutes")
            spec_minutes = float(comp.value) * UNIT_TO_MINUTES.get(str(spec_unit).lower(), 1.0)
            if abs(req_minutes - spec_minutes) > 1e-9:
                findings.append(Finding(
                    id=f"UNIT_MISMATCH:{req.id}:{rule.id}", severity="blocker",
                    kind="UNIT_MISMATCH", rule_ref=req.rule_ref, artifact=req.doc,
                    version=req.version, location=req.location,
                    evidence=[f"requirement {value} {base} = {req_minutes} minutes",
                              f"spec rule {rule.id} {comp.value} {spec_unit} = {spec_minutes} minutes"],
                    message=f"Requirement {req.id} and spec rule {rule.id} disagree after unit "
                            "normalisation.",
                    correction="Normalise both artifacts to one declared time unit.",
                ))


def _branch_coverage(bundle: Bundle, programs: dict[str, DecisionProgram],
                     findings: list[Finding]) -> None:
    required_routes = {r.route for r in programs["requirements"].rules}
    required_routes |= {programs["requirements"].default_route}
    flow_routes = {r.route for r in programs["workflow"].rules}
    flow_routes |= {programs["workflow"].default_route}
    for route in sorted(required_routes - flow_routes - {ROUTE_UNKNOWN}):
        findings.append(Finding(
            id=f"MISSING_WORKFLOW_BRANCH:{route}", severity="blocker", kind="MISSING_BRANCH",
            rule_ref=None, artifact=bundle.workflow.artifact_id, version=bundle.workflow.version,
            location="workflow paths", evidence=[f"required route '{route}' has no workflow path"],
            message=f"Workflow has no branch reaching '{route}'.",
            correction=f"Add a workflow branch whose terminal destination is '{route}'.",
        ))
    flow_refs = {n.source_ref for n in bundle.workflow.nodes if n.source_ref}
    for req in bundle.requirements:
        if req.text.strip().lower().startswith(("otherwise", "else", "all remaining")):
            continue
        if req.rule_ref not in flow_refs:
            findings.append(Finding(
                id=f"WORKFLOW_UNLINKED_REQUIREMENT:{req.rule_ref}", severity="major",
                kind="MISSING_SOURCE_REFERENCE", rule_ref=req.rule_ref,
                artifact=bundle.workflow.artifact_id, version=bundle.workflow.version,
                location="workflow nodes",
                evidence=[f"no workflow node cites {req.rule_ref}"],
                message=f"No workflow node is linked to requirement {req.rule_ref}.",
                correction="Attach source_ref to the corresponding decision node.",
            ))


def run_deterministic_review(bundle: Bundle, config: ReviewConfig) -> ReviewContext:
    hashes = bundle_hashes(bundle)
    ctx = ReviewContext(
        bundle=bundle, config=config,
        approvals=derive_effective_requirements(
            bundle.requirements, bundle.approvals, hashes),
        programs={}, hashes=hashes,
        known_refs={r.id for r in bundle.requirements} | {r.rule_ref for r in bundle.requirements}
                   | {r.id for r in bundle.spec.rules},
        known_anchors=_anchor_set(bundle),
        model_required=config.model_required,
    )
    ctx.findings.extend(ctx.approvals.findings)

    total_chars = len(bundle.model_dump_json())
    if total_chars > config.max_input_chars:
        ctx.findings.append(Finding(
            id="INPUT_TOO_LARGE", severity="major", kind="UNREVIEWED_SCOPE",
            rule_ref=None, artifact="bundle", version=bundle.spec.version, location="input",
            evidence=[f"{total_chars} chars > {config.max_input_chars} limit"],
            message="Input exceeds the configured review limit; it was not silently truncated.",
            correction="Split the bundle into smaller review units or raise the configured limit.",
        ))
        ctx.unreviewed.append("input:oversized")

    units = bundle.spec.feature_units
    req_program, req_findings, req_unreviewed = compile_requirements(ctx.approvals.effective, units)
    spec_program, spec_findings, spec_unreviewed = compile_spec(bundle.spec)
    flow_program, flow_findings, flow_unreviewed, _ = compile_workflow(bundle.workflow, units)
    ctx.programs.update(requirements=req_program, spec=spec_program, workflow=flow_program)

    for collection in (req_findings, spec_findings, flow_findings):
        ctx.findings.extend(collection)
    for item in (req_unreviewed + spec_unreviewed + flow_unreviewed):
        ctx.unreviewed.append(item)
    ctx.oracle_incomplete = bool(req_unreviewed)

    code_programs: list[DecisionProgram] = []
    for snippet in bundle.snippets:
        ok, syntax_error = syntax_check(snippet)
        if not ok:
            ctx.findings.append(Finding(
                id=f"CODE_SYNTAX_ERROR:{snippet.path}", severity="blocker", kind="CODE_SYNTAX_ERROR",
                rule_ref=snippet.source_ref, artifact=snippet.artifact_id, version=snippet.version,
                location=snippet.location or snippet.path, evidence=[syntax_error],
                message=f"Syntax error in {snippet.path}: {syntax_error}",
                correction="Fix the syntax before review.",
            ))
            ctx.unreviewed.append(f"code:{snippet.path}")
            continue
        parsed = inspect_snippet(snippet, units)
        for claim in parsed.approval_claims:
            ctx.findings.append(Finding(
                id=f"UNAUTHORIZED_APPROVAL_CLAIM:{snippet.path}:{claim.lower()}",
                severity="major", kind="UNAUTHORIZED_APPROVAL_CLAIM",
                rule_ref=snippet.source_ref, artifact=snippet.artifact_id, version=snippet.version,
                location=snippet.location or snippet.path,
                evidence=[f"code comment claim '{claim}'"],
                message=f"Code comment in {snippet.path} claims approval ('{claim}'). Comments "
                        "cannot grant approval authority.",
                correction="Remove the claim; use top-level approval metadata.",
            ))
        for unsupported in parsed.unsupported:
            ctx.findings.append(Finding(
                id=f"UNSUPPORTED_PYTHON:{snippet.path}", severity="major", kind="UNSUPPORTED_PYTHON",
                rule_ref=snippet.source_ref, artifact=snippet.artifact_id, version=snippet.version,
                location=snippet.location or snippet.path, evidence=[unsupported],
                message=f"{snippet.path}: {unsupported}",
                correction="Rewrite using the documented restricted Python subset.",
            ))
            ctx.unreviewed.append(f"code:{snippet.path}:unsupported")
        if parsed.error:
            ctx.findings.append(Finding(
                id=f"CODE_INSPECTION_FAILED:{snippet.path}", severity="major",
                kind="UNSUPPORTED_PYTHON", rule_ref=snippet.source_ref,
                artifact=snippet.artifact_id, version=snippet.version,
                location=snippet.location or snippet.path, evidence=[parsed.error],
                message=f"Cannot inspect {snippet.path}: {parsed.error}",
                correction="Use only the supported decision-function subset.",
            ))
            ctx.unreviewed.append(f"code:{snippet.path}")
            continue
        assert parsed.program is not None
        code_programs.append(parsed.program)
        ctx.programs[f"code:{snippet.path}"] = parsed.program

        if config.execute_code and code_programs:
            sample = Ticket(category="billing", urgent=False, waiting_minutes=31)
            predicted = eval_program(parsed.program, sample)
            actual, err = execute_code(snippet, sample)
            if err:
                ctx.findings.append(Finding(
                    id=f"CODE_EXECUTION_FAILED:{snippet.path}", severity="major",
                    kind="EXECUTION_FAILURE", rule_ref=snippet.source_ref,
                    artifact=snippet.artifact_id, version=snippet.version,
                    location=snippet.location or snippet.path, evidence=[err],
                    message=f"Execution of {snippet.path} failed: {err}",
                    correction="Inspect the snippet; execution is opt-in and separate.",
                ))
            elif actual != predicted:
                ctx.findings.append(Finding(
                    id=f"EXECUTION_DISAGREEMENT:{snippet.path}", severity="blocker",
                    kind="SCRIPT_DISAGREEMENT", rule_ref=snippet.source_ref,
                    artifact=snippet.artifact_id, version=snippet.version,
                    location=snippet.location or snippet.path,
                    evidence=[f"AST predicted {predicted}", f"execution returned {actual}"],
                    message=f"Execution of {snippet.path} disagrees with static inspection.",
                    correction="Align the executed behaviour with the inspected decision logic.",
                    expected_route=predicted, actual_route=actual, counterexample=sample,
                ))

    _source_coverage(bundle, ctx.findings)
    _unit_consistency(bundle, ctx.findings)
    _branch_coverage(bundle, ctx.programs, ctx.findings)

    all_programs = list(ctx.programs.values())
    domain = build_domain(all_programs,
                          sampled=config.enable_ablation, sample_size=8)
    ctx.domain_size = domain.size
    ctx.coverage_mode = "sampled" if config.enable_ablation else "exhaustive"
    if ctx.unreviewed:
        ctx.coverage_mode = "partial" if not config.enable_ablation else "sampled"

    others = [p for name, p in ctx.programs.items() if name != "requirements"]
    divergences, counts = compare_programs(req_program, others, domain)
    ctx.divergences = divergences
    for d in divergences:
        kind = classify_divergence(d, req_program, ctx.programs[d.origin])
        ctx.findings.append(_divergence_finding(
            d, req_program, ctx.programs[d.origin], kind, ctx.oracle_incomplete))

    for a, b, ticket, ra, rb in pairwise_compare(others, domain):
        ctx.findings.append(Finding(
            id=f"CROSS_ARTIFACT_DRIFT:{a}:{b}", severity="major", kind="SCRIPT_DISAGREEMENT",
            rule_ref=None, artifact=b, version=ctx.programs[b].version,
            location="compiled decision paths",
            evidence=[f"{a}={ra}", f"{b}={rb}", ticket.model_dump_json()],
            message=f"{a} and {b} disagree on a concrete ticket: {ra} vs {rb}.",
            correction=f"Reconcile {a} and {b}; both must match the effective requirements.",
            counterexample=ticket, expected_route=ra, actual_route=rb,
        ))

    ctx.check_results.append(CheckResult(
        name="source_coverage", passed=not any(f.kind == "OMITTED_REQUIREMENT" for f in ctx.findings),
        exhaustive=True, detail=f"{len(bundle.requirements)} source requirements checked",
    ))
    ctx.check_results.append(CheckResult(
        name="approval_reconciliation", passed=not ctx.approvals.has_blocker,
        exhaustive=True, detail=f"{len(bundle.approvals)} approval records checked",
    ))
    for origin, stats in counts.items():
        ctx.check_results.append(CheckResult(
            name=f"equivalence:{origin}", passed=stats["mismatches"] == 0,
            exhaustive=not config.enable_ablation, partitions=stats["partitions"],
            detail=f"{stats['mismatches']} mismatching partitions of {stats['partitions']}",
        ))
    return ctx


def derive_status(ctx: ReviewContext, model_findings: list[Finding] | None = None
                  ) -> tuple[str, str]:
    all_findings = ctx.findings + (model_findings or [])
    blockers = [f for f in all_findings if f.severity == "blocker"]
    if blockers:
        return "CHANGES_REQUIRED", (
            f"{len(blockers)} evidenced blocker(s) across {len(all_findings)} finding(s).")
    model_failure = any(
        f.origin == "model" and f.kind in ("MODEL_TIMEOUT", "MODEL_JSON_INVALID")
        for f in (model_findings or [])
    )
    if ctx.unreviewed or ctx.approvals.has_blocker or model_failure:
        reason = (f"{len(ctx.unreviewed)} unreviewed item(s)" if ctx.unreviewed
                  else "a required model check failed")
        return "INCOMPLETE", (
            f"Full review prevented by {reason}; no blocker established.")
    return "PASS", (
        f"All effective requirements reviewed exhaustively over {ctx.domain_size} "
        "representative inputs with no blocker.")


def build_report(ctx: ReviewContext, model_findings: list[Finding] | None = None,
                 provenance=None) -> ReviewReport:
    status, summary = derive_status(ctx, model_findings)
    findings = ctx.findings + (model_findings or [])
    coverage = Coverage(
        mode=ctx.coverage_mode,
        supported_scope="documented source patterns, structured guards, acyclic workflows, "
                        "restricted Python subset",
        reviewed_requirements=[r.rule_ref for r in ctx.bundle.requirements],
        unreviewed=[{"scope": item, "reason": "outside supported scope or missing evidence"}
                    for item in ctx.unreviewed],
        partitions_tested=ctx.domain_size,
        artifacts_reviewed=list(ctx.programs),
    )
    hashes = dict(ctx.hashes)
    return ReviewReport(
        status=status, summary=summary, findings=findings, coverage=coverage,
        check_results=ctx.check_results, model=provenance,
        content_hashes=hashes, config_signature=ctx.config.signature(),
    )
