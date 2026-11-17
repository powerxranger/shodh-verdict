"""Capture a full report for one synthetic case into a file (used by debug logs)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.make_demo import make_bundle
from verdict.config import ReviewConfig
from verdict.pipeline import review_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case")
    parser.add_argument("out")
    parser.add_argument("--ablate", action="store_true")
    args = parser.parse_args()
    bundle = make_bundle(args.case)
    config = ReviewConfig.from_env(**bundle.config, enable_ablation=args.ablate)
    report = review_bundle(bundle, config, use_cache=False)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    print(json.dumps({"status": report.status, "summary": report.summary,
                      "findings": [f.kind for f in report.findings]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
