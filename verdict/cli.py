"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ReviewConfig
from .models import Bundle
from .pipeline import review_bundle, review_file, save_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verdict", description=__doc__)
    parser.add_argument("bundle", nargs="?", help="path to a JSON bundle")
    parser.add_argument("--demo", action="store_true", help="run the built-in synthetic demo")
    parser.add_argument(
        "--format", choices=("json", "text"), default="json",
        help="report output format (default: json; text is human-readable)",
    )
    parser.add_argument("--out", help="write the report to this path in --format")
    parser.add_argument("--scenario", help="fake model scenario")
    parser.add_argument("--ablate", action="store_true", help="disable exhaustive equivalence")
    parser.add_argument("--require-model", action="store_true")
    parser.add_argument("--execute-code", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)

    config = ReviewConfig.from_env(
        **({"model_scenario": args.scenario} if args.scenario else {}),
        enable_ablation=args.ablate or ReviewConfig.from_env().enable_ablation,
        model_required=args.require_model or ReviewConfig.from_env().model_required,
        execute_code=args.execute_code or ReviewConfig.from_env().execute_code,
    )

    if args.demo:
        from scripts.make_demo import make_demo_bundle
        bundle = make_demo_bundle()
    elif args.bundle:
        bundle = None
        report = review_file(args.bundle, config, use_cache=not args.no_cache)
        return _emit(report, args.out, args.format)
    else:
        parser.error("provide a bundle path or --demo")

    report = review_bundle(bundle, config, use_cache=not args.no_cache)
    return _emit(report, args.out, args.format)


def _emit(report, out: str | None, fmt: str = "json") -> int:
    payload = report.to_json() if fmt == "json" else report.to_text()
    if out:
        save_report(report, out, fmt=fmt)
        print(f"Wrote {report.status} {fmt} report to {out}")
    else:
        print(payload)
    return 0 if report.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
