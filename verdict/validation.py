"""Validation gate for model reports.

Rejects malformed JSON (with strictly bounded repair), invented references,
unresolved evidence, conflicting claims and coverage overclaims. Failed
required model checks are never converted into a PASS.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .config import ReviewConfig
from .models import Finding, ModelProvenance
from .model_client import ModelRequest, ModelResponse

INJECTION_RE = re.compile(
    r"ignore (?:all |any )?(?:prior|previous|above) (?:rules|instructions)|"
    r"set status (?:to )?pass|you are now|disregard (?:the )?(?:system|reviewer)",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    parsed: dict | None = None
    accepted: list[Finding] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    parse_ok: bool = False
    notes: list[str] = field(default_factory=list)


def _repair(text: str, max_attempts: int) -> tuple[dict | None, list[str]]:
    notes: list[str] = []
    candidates = [text.strip()]
    fenced = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    candidates.append(fenced)
    if candidates[-1].startswith("{"):
        candidates.append(candidates[-1].rstrip().rstrip(",") + "}")
        candidates.append(candidates[-1].rstrip().rstrip(",") + ']}')
    for i, candidate in enumerate(candidates[: max(1, max_attempts + 1)]):
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                if i:
                    notes.append(f"repaired JSON on attempt {i}")
                return value, notes
        except json.JSONDecodeError:
            continue
    return None, notes + ["all bounded JSON repair attempts failed"]


def _provenance(client_name: str, scenario: str, request: ModelRequest,
                response: ModelResponse) -> ModelProvenance:
    return ModelProvenance(
        client=client_name, scenario=scenario,
        request_config={
            "prompt_sha256": request.signature(),
            "max_retries": request.config.max_model_retries,
            "max_tokens": request.config.max_model_tokens,
        },
        response_sha256=response.sha256, attempts=response.attempts,
        tokens_used=response.tokens_used, failures=response.failures,
        real_model=response.real_model,
    )


def _trust_finding(fid: str, severity: str, kind: str, message: str,
                   correction: str, evidence: list[str]) -> Finding:
    return Finding(
        id=fid, severity=severity, kind=kind, artifact="model", version="n/a",
        location="model response", evidence=evidence, message=message,
        correction=correction, origin="model",
    )


def validate_model_response(
    response: ModelResponse,
    client_name: str,
    request: ModelRequest,
    config: ReviewConfig,
    known_refs: set[str],
    known_anchors: set[str],
    coverage_mode: str,
    deterministic_refs: set[str],
) -> tuple[ValidationResult, ModelProvenance]:
    result = ValidationResult()
    provenance = _provenance(client_name, response.scenario, request, response)

    if not response.text.strip():
        result.findings.append(_trust_finding(
            "MODEL_TIMEOUT", "major", "MODEL_TIMEOUT",
            "Model client returned no response: " + "; ".join(response.failures),
            "Retry with a working model or disable the required-model setting.", response.failures))
        return result, provenance

    parsed, notes = _repair(response.text, config.max_model_retries)
    result.notes.extend(notes)
    if parsed is None:
        result.findings.append(_trust_finding(
            "MODEL_JSON_INVALID", "major", "MODEL_JSON_INVALID",
            "Model response was not valid JSON after bounded repair.",
            "Constrain the model to produce a single JSON object.", [response.text[:200]]))
        return result, provenance

    result.parsed = parsed
    result.parse_ok = True

    if INJECTION_RE.search(response.text):
        result.findings.append(_trust_finding(
            "MODEL_OUTPUT_INJECTION", "major", "PROMPT_INJECTION",
            "Model output contained an instruction-like claim; it was ignored.",
            "Keep system prompt and data boundaries intact.", [response.text[:200]]))

    claim = str(parsed.get("coverage_claim", ""))
    if coverage_mode != "exhaustive" and re.search(r"\bfull\b|\ball prose\b|\bverified\b", claim, re.I):
        result.findings.append(_trust_finding(
            "MODEL_COVERAGE_OVERCLAIM", "major", "COVERAGE_OVERCLAIM",
            f"Model claims '{claim}' but review coverage is '{coverage_mode}'.",
            "Restrict claims to reviewed scope.", [claim]))

    seen_by_ref: dict[str, list[dict]] = {}
    for idx, raw in enumerate(parsed.get("findings", []) or []):
        if not isinstance(raw, dict):
            result.findings.append(_trust_finding(
                f"MODEL_FINDING_INVALID:{idx}", "major", "INVALID_MODEL_REPORT",
                "Finding is not an object.", "Return objects with the documented keys.", []))
            continue
        ref = raw.get("rule_ref")
        evidence = [str(e) for e in (raw.get("evidence") or [])]
        if ref and ref not in known_refs:
            result.findings.append(_trust_finding(
                f"INVALID_MODEL_REFERENCE:{ref}", "major", "INVENTED_REFERENCE",
                f"Model cited unknown rule reference '{ref}'.",
                "Cite only references from the supplied registry.", evidence))
            continue
        resolved = [e for e in evidence if any(anchor in e for anchor in known_anchors)]
        if not resolved:
            result.findings.append(_trust_finding(
                f"UNRESOLVED_MODEL_EVIDENCE:{ref or idx}", "major", "UNRESOLVED_EVIDENCE",
                f"Model evidence for '{ref}' does not resolve to any known anchor.",
                "Cite a concrete artifact@version:location anchor.", evidence))
            continue
        severity = str(raw.get("severity", "minor")).lower()
        if severity not in ("blocker", "major", "minor", "info"):
            severity = "minor"
        # A model blocker is only promoted when it agrees with the deterministic
        # review domain. Otherwise it is advisory.
        if severity == "blocker" and ref not in deterministic_refs:
            severity = "major"
        seen_by_ref.setdefault(str(ref), []).append(raw)
        finding = Finding(
            id=f"MODEL_FINDING:{idx}:{ref}", severity=severity,
            kind=str(raw.get("kind", "MODEL_ANNOTATION")), rule_ref=ref,
            artifact=str(raw.get("artifact", "model")),
            version=str(raw.get("version", "n/a")),
            location=str(raw.get("location", "n/a")),
            evidence=resolved, message=str(raw.get("message", "")),
            correction=str(raw.get("correction", "Review manually.")),
            origin="model",
        )
        result.accepted.append(finding)

    for ref, items in seen_by_ref.items():
        msgs = {str(i.get("message", "")) for i in items}
        if len(items) > 1 and len(msgs) > 1 and any(
            i.get("severity") == "blocker" for i in items
        ):
            result.findings.append(_trust_finding(
                f"CONFLICTING_MODEL_CLAIMS:{ref}", "major", "CONFLICTING_MODEL_CLAIMS",
                f"Model produced conflicting claims for {ref}: {sorted(msgs)}.",
                "Require one internally consistent report.", [ref]))
            result.accepted = [f for f in result.accepted if f.rule_ref != ref]

    return result, provenance
