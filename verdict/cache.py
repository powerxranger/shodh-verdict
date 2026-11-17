"""Content-addressed report cache.

The key includes hashes of every artifact AND all approval records AND the run
configuration signature. Changing any input therefore cannot reuse a stale
passing report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import Bundle, ReviewReport
from .config import ReviewConfig

CACHE_DIR = Path(__file__).resolve().parent.parent / ".verdict_cache"


def bundle_hashes(bundle: Bundle) -> dict[str, str]:
    parts = {
        "requirements": [r.model_dump() for r in bundle.requirements],
        "spec": bundle.spec.model_dump(),
        "workflow": bundle.workflow.model_dump(),
        "snippets": [s.model_dump() for s in bundle.snippets],
        "approvals": [a.model_dump() for a in bundle.approvals],
    }
    return {
        name: hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
        for name, value in parts.items()
    }


def cache_key(bundle: Bundle, config: ReviewConfig) -> str:
    payload = json.dumps({**bundle_hashes(bundle), "config": config.signature()}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def load(key: str) -> ReviewReport | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        report = ReviewReport.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if report.status == "PASS" and report.content_hashes.get("__key__") != key:
        return None
    return report


def store(key: str, report: ReviewReport) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(report.to_json())
    data.setdefault("content_hashes", {})["__key__"] = key
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8")


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    files = list(CACHE_DIR.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)
