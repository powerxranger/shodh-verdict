"""Top-level orchestration across all four stages."""

from __future__ import annotations

import json
from pathlib import Path

from . import cache
from .config import ReviewConfig
from .models import Bundle, ReviewReport
from .model_client import ModelRequest, build_prompt, make_client
from .review import ReviewContext, build_report, run_deterministic_review
from .validation import validate_model_response


def _untrusted_payload(bundle: Bundle) -> str:
    parts = ["Requirements (untrusted prose):"]
    parts += [f"- {r.id}: {r.text} [{r.doc}@{r.version}:{r.location}]"
              for r in bundle.requirements]
    parts.append("Specification notes (untrusted):")
    parts += [f"- {r.id}: {r.notes or ''}" for r in bundle.spec.rules]
    parts.append("Code comments (untrusted):")
    parts += [f"- {s.path}:\n{s.code}" for s in bundle.snippets]
    return "\n".join(parts)


def review_bundle(bundle: Bundle, config: ReviewConfig | None = None,
                  use_cache: bool = True) -> ReviewReport:
    config = config or ReviewConfig.from_env()
    key = cache.cache_key(bundle, config)
    if use_cache:
        cached = cache.load(key)
        if cached is not None:
            return cached

    ctx: ReviewContext = run_deterministic_review(bundle, config)

    request = ModelRequest(
        system=build_prompt.__doc__ or "",
        prompt=_untrusted_payload(bundle),
        config=config,
        known_refs=sorted(ctx.known_refs),
        known_anchors=sorted(ctx.known_anchors),
    )
    client = make_client(request)
    response = client.generate(request)
    validation, provenance = validate_model_response(
        response=response,
        client_name=client.name,
        request=request,
        config=config,
        known_refs=ctx.known_refs,
        known_anchors=ctx.known_anchors,
        coverage_mode=ctx.coverage_mode,
        deterministic_refs={f.rule_ref for f in ctx.findings if f.rule_ref},
    )
    model_findings = validation.accepted + validation.findings

    report = build_report(ctx, model_findings, provenance)
    if use_cache:
        cache.store(key, report)
    return report


def review_file(path: str | Path, config: ReviewConfig | None = None,
                use_cache: bool = True) -> ReviewReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return review_bundle(Bundle.model_validate(data), config, use_cache)


def save_report(report: ReviewReport, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report.to_json() + "\n", encoding="utf-8")
