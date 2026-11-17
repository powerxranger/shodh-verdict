"""Central configuration and constants for Verdict."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

ROUTE_MANUAL = "manual_review"
ROUTE_PRIORITY = "priority_queue"
ROUTE_ESCALATION = "escalation"
ROUTE_NORMAL = "normal_queue"
ROUTE_UNKNOWN = "UNROUTED"

ROUTES = (ROUTE_MANUAL, ROUTE_PRIORITY, ROUTE_ESCALATION, ROUTE_NORMAL)

ROUTE_ALIASES = {
    "manual review": ROUTE_MANUAL,
    "manual_review": ROUTE_MANUAL,
    "manual": ROUTE_MANUAL,
    "priority queue": ROUTE_PRIORITY,
    "priority_queue": ROUTE_PRIORITY,
    "priority": ROUTE_PRIORITY,
    "escalation": ROUTE_ESCALATION,
    "escalate": ROUTE_ESCALATION,
    "normal queue": ROUTE_NORMAL,
    "normal_queue": ROUTE_NORMAL,
    "normal": ROUTE_NORMAL,
}

MISSING = "__MISSING__"
OTHER = "__OTHER__"

FEATURE_CATEGORY = "category"
FEATURE_URGENT = "urgent"
FEATURE_WAITING = "waiting_minutes"

TIME_FEATURES = {FEATURE_WAITING}
BASE_TIME_UNIT = "minutes"
UNIT_TO_MINUTES = {
    "minute": 1.0,
    "minutes": 1.0,
    "min": 1.0,
    "mins": 1.0,
    "hour": 60.0,
    "hours": 60.0,
    "hr": 60.0,
    "hrs": 60.0,
    "second": 1.0 / 60.0,
    "seconds": 1.0 / 60.0,
    "sec": 1.0 / 60.0,
    "secs": 1.0 / 60.0,
}


def canonical_route(raw: str | None) -> str:
    if raw is None:
        return ROUTE_UNKNOWN
    key = str(raw).strip().lower().replace("-", "_")
    return ROUTE_ALIASES.get(key, key)


@dataclass(frozen=True)
class ReviewConfig:
    """Immutable run configuration. Changes invalidate the content cache."""

    max_model_retries: int = 2
    max_model_tokens: int = 4000
    max_input_chars: int = 200_000
    model_required: bool = False
    model_scenario: str = "valid_clean"
    enable_ablation: bool = False
    execute_code: bool = False

    @classmethod
    def from_env(cls, **overrides) -> "ReviewConfig":
        base = dict(
            max_model_retries=int(os.getenv("VERDICT_MAX_RETRIES", "2")),
            max_model_tokens=int(os.getenv("VERDICT_MAX_TOKENS", "4000")),
            max_input_chars=int(os.getenv("VERDICT_MAX_INPUT_CHARS", "200000")),
            model_required=os.getenv("VERDICT_MODEL_REQUIRED", "0") == "1",
            model_scenario=os.getenv("VERDICT_MODEL_SCENARIO", "valid_clean"),
            enable_ablation=os.getenv("VERDICT_ABLATE", "0") == "1",
            execute_code=os.getenv("VERDICT_EXECUTE_CODE", "0") == "1",
        )
        base.update(overrides)
        return cls(**base)

    def signature(self) -> str:
        return "|".join(f"{k}={v}" for k, v in sorted(vars(self).items()))
