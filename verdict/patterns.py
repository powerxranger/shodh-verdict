"""Supported source-language patterns and a deterministic recursive-descent parser.

Supported grammar (documented in CONTRACTS.md):

    requirement   := clause ([";"|","] clause)*
    clause        := ["except when"|"except if"|"unless"] condition "->" route
                   | "otherwise" "->" route
    condition     := or_expr
    or_expr       := and_expr ("or" and_expr)*
    and_expr      := not_expr ("and" not_expr)*
    not_expr      := "not" not_expr | "(" condition ")" | comparison
    comparison    := feature op value [unit]
                   | feature "is" "missing" | "missing" feature
                   | feature
    feature       := category | urgent | waiting_minutes
    op            := "==" | "!=" | ">=" | ">" | "<=" | "<"
    unit          := minutes | hours | seconds (aliases supported)

Anything outside this grammar is reported as UNSUPPORTED_SOURCE_PATTERN and
stays visible as unreviewed scope; it is never silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import ROUTE_ALIASES, canonical_route, canonical_route as _route
from .models import SourceRequirement
from .programs import Guard, cmp, from_model
from .models import GuardModel, ComparisonModel

OP_WORDS = {
    "at least": ">=",
    "no less than": ">=",
    "greater than or equal to": ">=",
    "at most": "<=",
    "no more than": "<=",
    "less than or equal to": "<=",
    "greater than": ">",
    "over": ">",
    "more than": ">",
    "less than": "<",
    "under": "<",
    "below": "<",
    "equals": "==",
    "equal to": "==",
    "is": "==",
    "not equal to": "!=",
    "differs from": "!=",
    "≥": ">=",
    "≤": "<=",
    "≠": "!=",
}

FEATURE_PHRASES = [
    ("waiting minutes", "waiting_minutes"),
    ("waiting time in minutes", "waiting_minutes"),
    ("waiting time", "waiting_minutes"),
    ("wait time", "waiting_minutes"),
    ("waiting", "waiting_minutes"),
    ("ticket category", "category"),
    ("category", "category"),
    ("urgency flag", "urgent"),
    ("is urgent", "urgent"),
    ("urgent ticket", "urgent"),
    ("urgent", "urgent"),
]

UNIT_WORDS = {
    "minute": "minutes", "minutes": "minutes", "min": "minutes", "mins": "minutes",
    "hour": "hours", "hourly": "hours", "hours": "hours", "hr": "hours", "hrs": "hours",
    "second": "seconds", "seconds": "seconds", "sec": "seconds", "secs": "seconds",
}

APPROVAL_CLAIM_RE = re.compile(
    r"\b(approved|approve|approval|signed[ -]?off|authori[sz]ed|okay(?:ed)?|greenlit|"
    r"accepted by (?:product|legal|the team))\b",
    re.IGNORECASE,
)


@dataclass
class ParsedClause:
    condition_text: str
    route: str
    is_exception: bool = False
    is_default: bool = False
    order: int = 0


@dataclass
class ParsedRequirement:
    requirement: SourceRequirement
    guard: Guard | None = None
    route: str | None = None
    exceptions: list[tuple[Guard, str, str]] = field(default_factory=list)
    is_default: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.guard is not None or self.is_default)


def _normalize(text: str) -> str:
    t = text.lower().strip()
    t = t.replace("→", "->").replace("=>", "->").replace("–", "-")
    t = t.replace("≥", " >= ").replace("≤", " <= ").replace("≠", " != ")
    t = re.sub(r"\s+", " ", t)
    for phrase, op in sorted(OP_WORDS.items(), key=lambda kv: -len(kv[0])):
        if phrase in ("is", "≥", "≤", "≠"):
            continue
        t = re.sub(rf"\b{re.escape(phrase)}\b", f" {op} ", t)
    # Only commas separate clauses; semicolons inside prose stay with the route text.
    t = t.replace(",", " , ")
    return t.strip()


def _canonicalise_features(text: str) -> str:
    for phrase, feature in FEATURE_PHRASES:
        text = re.sub(rf"\b{re.escape(phrase)}\b", feature, text)
    return text


TOKEN_RE = re.compile(
    r"\s*(?:(>=|<=|!=|==|>|<)|('[^']*'|\"[^\"]*\")|(\d+(?:\.\d+)?)|([a-z_][a-z0-9_]*)|(\S))"
)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            break
        op, string, number, word, other = m.groups()
        if op or string or number or word:
            tokens.append(op or string or number or word)
        else:
            tokens.append(other)
        pos = m.end()
    return tokens


class ConditionParser:
    def __init__(self, tokens: list[str], feature_units: dict[str, str] | None = None):
        self.tokens = tokens
        self.i = 0
        self.feature_units = feature_units or {}
        self.warnings: list[str] = []

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ValueError("unexpected end of condition")
        self.i += 1
        return tok

    def accept(self, word: str) -> bool:
        if self.peek() == word:
            self.i += 1
            return True
        return False

    def parse(self) -> Guard:
        guard = self.or_expr()
        if self.i != len(self.tokens):
            raise ValueError(f"unexpected token '{self.peek()}'")
        return guard

    def or_expr(self) -> Guard:
        from .programs import OR
        parts = [self.and_expr()]
        while self.accept("or"):
            parts.append(self.and_expr())
        return parts[0] if len(parts) == 1 else OR(*parts)

    def and_expr(self) -> Guard:
        from .programs import AND, NOT
        parts = [self.not_expr()]
        while self.accept("and"):
            parts.append(self.not_expr())
        return parts[0] if len(parts) == 1 else AND(*parts)

    def not_expr(self) -> Guard:
        from .programs import NOT
        if self.accept("not"):
            return NOT(self.not_expr())
        if self.accept("("):
            guard = self.or_expr()
            if not self.accept(")"):
                raise ValueError("missing closing parenthesis")
            return guard
        return self.comparison()

    def comparison(self) -> Guard:
        tok = self.take().lower()
        if tok == "missing":
            feature = self.take().lower()
            return cmp(feature, "==", None)
        feature = tok
        if self.peek() == "is" and self.i + 1 < len(self.tokens) \
                and self.tokens[self.i + 1].lower() == "missing":
            self.take()
            self.take()
            return cmp(feature, "==", None)
        op = self.peek()
        if op not in ("==", "!=", ">=", ">", "<=", "<"):
            # bare feature => truthy flag (e.g. "urgent")
            return cmp(feature, "==", True)
        self.take()
        raw = self.take()
        if raw.startswith(("'", '"')):
            value: object = raw[1:-1]
        elif re.fullmatch(r"\d+(?:\.\d+)?", raw):
            value = float(raw) if "." in raw else int(raw)
        else:
            raise ValueError(f"unsupported value '{raw}'")
        unit = None
        nxt = self.peek()
        if nxt and nxt.lower() in UNIT_WORDS:
            unit = UNIT_WORDS[self.take().lower()]
        elif feature in self.feature_units:
            unit = self.feature_units[feature]
        gm = GuardModel(
            kind="cmp",
            comparison=ComparisonModel(feature=feature, op=op, value=value, unit=unit),
        )
        guard, warnings = from_model(gm, self.feature_units)
        self.warnings.extend(warnings)
        return guard


def parse_condition(text: str, feature_units: dict[str, str] | None = None
                    ) -> tuple[Guard | None, list[str], str | None]:
    try:
        normalized = _canonicalise_features(_normalize(text))
        parser = ConditionParser(tokenize(normalized), feature_units)
        guard = parser.parse()
        return guard, parser.warnings, None
    except (ValueError, AssertionError, IndexError) as exc:
        return None, [], str(exc)


def split_clauses(text: str) -> list[str]:
    normalized = _normalize(text)
    return [c.strip() for c in normalized.split(" , ") if c.strip()]


def parse_requirement(req: SourceRequirement,
                      feature_units: dict[str, str] | None = None) -> ParsedRequirement:
    result = ParsedRequirement(requirement=req)
    result.warnings.extend(find_approval_claims(req.text))
    clauses = split_clauses(req.text)
    if not clauses:
        result.error = "empty requirement"
        return result

    for idx, clause in enumerate(clauses):
        is_exception = bool(re.match(r"^(except|unless)\b", clause))
        if is_exception:
            clause = re.sub(r"^(except\s+(?:when|if)|unless)\s+", "", clause)
        if "->" not in clause:
            result.error = f"no route arrow in clause '{clause}'"
            return result
        condition_text, route_text = clause.split("->", 1)
        condition_text = condition_text.strip()
        route = extract_route(route_text)
        if route == "unrouted":
            result.error = f"unsupported route '{route_text.strip()}'"
            return result

        if condition_text.startswith("otherwise") or condition_text in ("else", "all remaining"):
            result.is_default = True
            result.route = route
            continue

        guard, warnings, error = parse_condition(condition_text, feature_units)
        result.warnings.extend(warnings)
        if error:
            result.error = f"{error} in '{condition_text}'"
            return result
        assert guard is not None
        if is_exception:
            result.exceptions.append((guard, route, condition_text))
        else:
            result.guard = guard
            result.route = route
    if result.guard is None and not result.is_default:
        result.error = "no main rule found"
    return result


def extract_route(route_text: str) -> str:
    """Find the first declared route phrase, ignoring trailing untrusted prose."""
    lowered = route_text.lower()
    for alias in sorted(ROUTE_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return canonical_route(alias)
    return canonical_route(lowered.strip())


def find_approval_claims(text: str) -> list[str]:
    """Detect approval-looking assertions inside untrusted prose or comments."""
    claims = []
    for match in APPROVAL_CLAIM_RE.finditer(text or ""):
        claims.append(match.group(0))
    return claims
