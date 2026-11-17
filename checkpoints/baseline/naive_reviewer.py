"""v0 BASELINE CHECKPOINT (deliberately naive - preserved, not used in production).

This is the initial working checkpoint. It checks rule-ID presence and numeric
substring overlap only. It has no decision-program compilation, no boundary
equivalence, no precedence analysis and no counterexample generation. It is
kept so the controlled evaluation can demonstrate what those mechanisms buy.

DO NOT USE FOR REAL REVIEWS.
"""

from __future__ import annotations

import json
import re
from typing import Any


def review(bundle: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    requirements = bundle.get("requirements", [])
    spec = bundle.get("spec", {})
    workflow = bundle.get("workflow", {})
    snippets = bundle.get("snippets", [])
    approvals = bundle.get("approvals", [])

    spec_refs = {r.get("source_ref") for r in spec.get("rules", [])}
    for req in requirements:
        ref = req["rule_ref"]
        if ref not in spec_refs and not req["text"].lower().startswith("otherwise"):
            findings.append({"kind": "OMITTED_REQUIREMENT", "rule_ref": ref,
                             "severity": "blocker"})

    approval_values: dict[tuple[str, str], set[str]] = {}
    for rec in approvals:
        key = (rec["scope_rule_id"], rec["scope_field"])
        approval_values.setdefault(key, set()).add(str(rec["proposed_value"]))
    for key, values in approval_values.items():
        if len(values) > 1 and all(
            a["approved"] for a in approvals
            if (a["scope_rule_id"], a["scope_field"]) == key
        ):
            findings.append({"kind": "CONTRADICTORY_APPROVALS", "rule_ref": key[0],
                             "severity": "blocker"})

    # Naive numeric substring check: only asks whether the number is mentioned.
    spec_text = json.dumps(spec)
    flow_text = json.dumps(workflow)
    code_text = " ".join(s.get("code", "") for s in snippets)
    for req in requirements:
        for number in re.findall(r"\d+", req["text"]):
            if number not in spec_text or number not in flow_text or number not in code_text:
                findings.append({"kind": "NAIVE_NUMBER_MISSING", "rule_ref": req["rule_ref"],
                                 "severity": "major"})

    blockers = [f for f in findings if f["severity"] == "blocker"]
    status = "CHANGES_REQUIRED" if blockers else "PASS"
    return {
        "status": status,
        "summary": "v0 naive ID/substring check",
        "findings": findings,
        "coverage": {"mode": "unverified", "partitions_tested": 0},
        "check_results": [],
        "model": None,
    }
