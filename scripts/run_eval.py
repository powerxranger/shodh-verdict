"""Frozen evaluation: generate cases, freeze hashes, compare baseline vs final."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checkpoints.baseline.naive_reviewer import review as baseline_review  # noqa: E402
from scripts.make_demo import CASE_IDS, make_bundle  # noqa: E402
from verdict.config import ReviewConfig  # noqa: E402
from verdict.models import Bundle  # noqa: E402
from verdict.pipeline import review_bundle  # noqa: E402

CASES_DIR = ROOT / "evals" / "frozen" / "cases"
MANIFEST = ROOT / "evals" / "frozen" / "manifest.json"
RESULTS = ROOT / "evals" / "results.json"


def _canonical_bytes(path: Path) -> bytes:
    """Hash text bytes independently of Windows CRLF vs Unix LF checkouts."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def freeze_cases() -> dict:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    entries = {}
    for case_id in CASE_IDS:
        bundle = make_bundle(case_id)
        payload = json.loads(bundle.model_dump_json())
        path = CASES_DIR / f"{case_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
        entries[case_id] = {
            "sha256": hashlib.sha256(_canonical_bytes(path)).hexdigest(),
            "expected_status": bundle.expected_status,
            "expected_finding_kinds": bundle.expected_finding_kinds,
            "config": bundle.config,
            "description": bundle.description,
        }
    MANIFEST.write_text(json.dumps({
        "frozen_set_version": "1.0",
        "note": "All artifacts are synthetic and generated from scripts/make_demo.py.",
        "cases": entries,
    }, indent=2), encoding="utf-8", newline="\n")
    return entries


def verify_freeze(manifest: dict) -> list[str]:
    problems = []
    for case_id, meta in manifest["cases"].items():
        path = CASES_DIR / f"{case_id}.json"
        if not path.exists():
            problems.append(f"{case_id}: missing file")
        elif hashlib.sha256(_canonical_bytes(path)).hexdigest() != meta["sha256"]:
            problems.append(f"{case_id}: hash mismatch")
    return problems


def run(ablate: bool = False, use_cache: bool = False) -> dict:
    if not MANIFEST.exists():
        freeze_cases()
    manifest = json.loads(MANIFEST.read_text())
    problems = verify_freeze(manifest)
    if problems:
        raise RuntimeError("Frozen set changed: " + "; ".join(problems))

    rows = []
    for case_id, meta in manifest["cases"].items():
        bundle = Bundle.model_validate_json((CASES_DIR / f"{case_id}.json").read_text())
        config_kwargs = dict(meta["config"])
        if ablate:
            config_kwargs["enable_ablation"] = True
        config = ReviewConfig.from_env(**config_kwargs)

        final = review_bundle(bundle, config, use_cache=use_cache)
        final_kinds = {f.kind for f in final.findings}
        final_ok = final.status == meta["expected_status"] and all(
            k in final_kinds for k in meta["expected_finding_kinds"])

        baseline = baseline_review(json.loads(bundle.model_dump_json()))
        baseline_ok = baseline["status"] == meta["expected_status"]

        rows.append({
            "case": case_id,
            "expected_status": meta["expected_status"],
            "expected_finding_kinds": meta["expected_finding_kinds"],
            "final_status": final.status,
            "final_finding_kinds": sorted(final_kinds),
            "final_correct": final_ok,
            "baseline_status": baseline["status"],
            "baseline_correct": baseline_ok,
            "partitions": final.coverage.partitions_tested,
            "coverage_mode": final.coverage.mode,
            "counterexamples": sum(1 for f in final.findings if f.counterexample),
        })

    summary = {
        "frozen_set_version": manifest["frozen_set_version"],
        "ablation": ablate,
        "total": len(rows),
        "final_correct": sum(r["final_correct"] for r in rows),
        "baseline_correct": sum(r["baseline_correct"] for r in rows),
        "rows": rows,
    }
    out = RESULTS.parent / f"results{'_ablation' if ablate else ''}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def markdown(summary: dict) -> str:
    lines = [
        "| Case | Expected | Final v1 | v1 OK | v0 baseline | v0 OK | Partitions | Counterexamples |",
        "|---|---|---|---|---|---|---:|---:|",
    ]
    for r in summary["rows"]:
        lines.append(
            f"| `{r['case']}` | {r['expected_status']} | {r['final_status']} | "
            f"{'yes' if r['final_correct'] else 'NO'} | {r['baseline_status']} | "
            f"{'yes' if r['baseline_correct'] else 'NO'} | {r['partitions']} | "
            f"{r['counterexamples']} |")
    lines += [
        "",
        f"**Totals:** final {summary['final_correct']}/{summary['total']} correct; "
        f"v0 baseline {summary['baseline_correct']}/{summary['total']} correct; "
        f"ablation={'ON' if summary['ablation'] else 'OFF'}.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ablate", action="store_true")
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--cache", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        freeze_cases()
        print("Frozen cases regenerated.")
        return 0
    summary = run(ablate=args.ablate, use_cache=args.cache)
    print(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
