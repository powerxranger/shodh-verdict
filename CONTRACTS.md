# Input contracts and supported language

All schemas are Pydantic models in `verdict/models.py`. Every artefact carries a version; every rule carries an `EvidenceAnchor` (`artifact`, `version`, `location`, optional `excerpt`) and a `source_ref`.

## Artefact schemas

| Artefact | Key fields |
|---|---|
| `SourceRequirement` | `id`, `text`, `doc`, `version`, `location`, `rule_ref`, `priority` |
| `StructuredSpec` | `version`, `artifact_id`, `default_route`, `feature_units`, `rules[]`, `rejected_suggestions[]` |
| `SpecRule` | `id`, `source_ref`, `guard`, `route`, `exceptions[]`, `priority`, `notes` |
| `Workflow` | `version`, `artifact_id`, `start`, `nodes[]` |
| `WorkflowNode` | `id`, `kind` (start/decision/terminal), `condition`, `true_next`, `false_next`, `destination`, `source_ref`, `location` |
| `PythonSnippet` | `version`, `artifact_id`, `path`, `function`, `code`, `source_ref`, `location` |
| `ApprovalRecord` | `change_id`, `scope_rule_id`, `scope_field`, `proposed_value`, `approved`, `version`, `applies_to`, `decided_by` |
| `Bundle` | all of the above + `id`, `expected_status`, `expected_finding_kinds`, `config` |

**Rule-reference mapping:** `SourceRequirement.rule_ref` ↔ `SpecRule.source_ref` ↔ `WorkflowNode.source_ref` ↔ `PythonSnippet.source_ref` (comma-separated for multiple). A requirement with no matching spec rule is an `OMITTED_REQUIREMENT` blocker. A spec rule with no `source_ref` is an `ORPHAN_SPEC_RULE` finding. Requirements with no source reference are impossible by construction (the source *is* the requirement); omissions in downstream artifacts receive an explicit `OMITTED_SOURCE:*` label in findings.

## Supported source-language patterns

```
requirement   := clause ("," clause)*
clause        := ["except when"|"except if"|"unless"] condition "->" route
               | "otherwise" "->" route
condition     := or_expr
or_expr       := and_expr ("or" and_expr)*
and_expr      := not_expr ("and" not_expr)*
not_expr      := "not" not_expr | "(" condition ")" | comparison
comparison    := feature op value [unit]
               | feature "is missing" | "missing" feature
               | feature                     (truthy flag, e.g. "urgent")
feature       := category | urgent | waiting_minutes  (aliases below)
op            := == | != | >= | > | <= | <
unit          := minutes | hours | seconds (and common aliases)
route         := manual review | priority queue | escalation | normal queue
```

Aliases: `waiting`, `waiting time`, `wait time` → `waiting_minutes`; `ticket category` → `category`; `urgent ticket`, `is urgent` → `urgent`. Operator phrases: `at least`/`no less than` → `>=`, `at most`/`no more than` → `<=`, `over`/`more than` → `>`, `under`/`less than`/`below` → `<`, `equals` → `==`. Unicode `→`, `≥`, `≤`, `≠` are accepted.

Trailing prose after a route is ignored for routing but scanned for approval claims and prompt injection; it is never silently trusted.

Examples that are verified in tests:

- `missing category -> manual review`
- `urgent ticket -> priority queue`
- `waiting >= 30 minutes -> escalation`
- `waiting < 30 minutes -> escalation`
- `(urgent or category == 'vip') and waiting >= 30 minutes -> priority queue`
- `waiting >= 30 minutes -> escalation, except when category == 'vip' -> priority queue`
- `waiting >= 0.5 hours -> escalation` (normalised to 30 minutes)

Anything outside this grammar produces `UNSUPPORTED_SOURCE_PATTERN` and appears in `coverage.unreviewed`.

## Restricted Python subset

Allowed: one function definition; `if`/`elif`/`else`; `return` of a string route constant; comparisons (`==`, `!=`, `>`, `>=`, `<`, `<=`, `is`, `is not`) between a named feature and a literal; `and`, `or`, `not`; parentheses; literal numbers, strings, booleans, `None`.

Rejected visibly: imports, calls, attribute access, subscripts, loops, comprehensions, lambdas, f-strings, assignments, decorators, nested functions, `try`/`raise`, non-literal returns. Syntax errors are a separate check from AST inspection.

Example accepted snippet:

```python
def route_ticket(category, urgent, waiting_minutes):
    if category is None:
        return 'manual_review'
    elif urgent:
        return 'priority_queue'
    elif waiting_minutes >= 30:
        return 'escalation'
    else:
        return 'normal_queue'
```

## Units

Time values are normalised to minutes (`UNIT_TO_MINUTES` in `config.py`). A comparison value's explicit `unit` wins; otherwise `spec.feature_units[feature]` is used; otherwise the base unit minutes is assumed and a warning is raised. Conflicting declarations across artifacts produce `UNIT_MISMATCH` blockers, while equivalent formulations (e.g. `0.5 hours` vs `30 minutes`) compare equal.

## Missing values

`None` in a ticket means missing. `feature is missing` / `missing feature` compiles to `feature == None`. Missing categorical values are a distinct member of the exhaustive domain, so "missing category" precedence is checked as a real input, not a special case in prose.

## Finding contract

Every finding has: `id`, `severity` (blocker/major/minor/info), `kind`, `rule_ref` (when available), `artifact`, `version`, `location`, `evidence[]`, `message`, `correction`, optional `expected_route`, `actual_route`, `counterexample` (concrete `Ticket`), and `origin` (deterministic/model/config).
