# Design rationale

## 1. The problem with "AI reviewer" demos

A prompt plus a similarity score cannot establish that a workflow implements a policy. Rule IDs can match while thresholds differ; metadata can be correct while the script routes differently; two plausible-looking rules can disagree only at one boundary. Verdict therefore treats the model as an *annotation layer* and puts correctness in a deterministic, inspectable core.

## 2. One semantic target: the `DecisionProgram`

All four artifacts compile to:

```
DecisionProgram = (ordered rules [(guard -> route)], default_route)
Guard           = comparison | AND | OR | NOT | true | false
Comparison      = (feature, op, normalised_value, declared_unit)
```

An ordered first-match program exactly captures the policy's precedence semantics. Compiling everything to the same form is what makes *behavioural* comparison possible rather than textual comparison.

- **Requirements** → parsed from the documented source grammar; approved changes applied first; exceptions scoped to their parent rule.
- **Specification** → structured guards converted directly; exceptions scoped to their rule.
- **Workflow** → DFS from `start` over reachable nodes only; `true` branch conjoins the condition, `false` branch conjoins its negation; terminal nodes yield path-guarded routes. Cycles, dangling links, unreachable nodes and missing destinations are findings.
- **Python** → AST allow-list walker with path guards; no execution required. Nested `if`/`elif`/`else` and fall-through are supported. Imports, calls, attributes, loops and comprehensions are rejected *visibly*.

## 3. Why the equivalence check is exhaustive

For the supported guard language, a comparison's truth value changes only:

1. at a boundary constant (`>= 30`, `== "vip"`, ...), or
2. somewhere in an open interval between two adjacent boundaries.

Therefore this finite domain is complete:

- numeric feature with boundaries `b1 < ... < bn` → `{b1−1, b1, (b1+b2)/2, b2, ..., (bn−1+bn)/2, bn, bn+1}` (exact `Fraction` arithmetic; no floating-point drift);
- boolean → `{true, false, missing}`;
- categorical → every compared constant + one `UNLISTED` sentinel + `missing`.

Two programs agreeing on the cross-product are equivalent **for every input expressible in the supported language**. Disagreement yields a concrete ticket, expected/actual routes, the matched rules and a partition count. This is materially stronger than sampling: the controlled ablation shows a false `PASS` when the mechanism is disabled.

We deliberately do **not** claim arbitrary-prose or arbitrary-Python verification. Unsupported content becomes `coverage.unreviewed` and forces `INCOMPLETE`.

## 4. Approval authority firewall

- Only `ApprovalRecord` instances (top-level metadata) can change effective requirements.
- Changes are applied by `(rule_id, field)`, ordered by `(version, change_id)`.
- Unapproved suggestions are recorded as `info` findings and never applied.
- Two approved records for the same scope with different values → `CONTRADICTORY_APPROVALS` blocker. No convenient version is chosen.
- The words "approved", "signed off", etc. inside requirement prose or code comments are detected as `UNAUTHORIZED_APPROVAL_CLAIM` findings and ignored for authority.
- The model prompt explicitly forbids the model from changing authority, and data is fenced in `<UNTRUSTED_DATA>`; attempted instructions in prose or model output are reported as prompt injection.

## 5. Status logic

```
if any blocker finding                  -> CHANGES_REQUIRED
elif unreviewed scope / required model failure -> INCOMPLETE
else                                    -> PASS
```

Model findings are advisory by default. A model "blocker" is promoted only when its rule reference exists in the registry, its evidence anchor resolves, and the rule is already in the deterministic review domain; otherwise it is downgraded to `major` and the trust failure itself is reported. This keeps model judgment useful without letting it override evidence.

## 6. Separation of code handling

| Path | Function | Default |
|---|---|---|
| Static inspection | `inspect_snippet` (AST allow-list) | always |
| Syntax check | `syntax_check` (`compile`) | always |
| Execution | `execute_code` (bounded subprocess) | **off**, `--execute-code` |

Arbitrary untrusted Python is never executed by default. When enabled, execution runs in a 2-second subprocess and any disagreement with static inspection is a blocker.

## 7. Caching

The cache key is SHA-256 of the canonical JSON of requirements + spec + workflow + snippets + **approvals** + config signature. Any artifact or approval change produces a new key, so a stale passing report cannot be reused. `content_hashes` are included in the report for audit.

## 8. Design choices deliberately rejected

- **Rule-ID matching** — IDs can match while semantics differ (v0 baseline demonstrates).
- **Numeric substring matching** — cannot detect precedence, scope, units or boundary exclusivity.
- **Similarity scores / polished prompts** — no counterexample, no proof, no status discipline.
- **Silently dropping unsupported content** — hides exactly the risk a reviewer must surface.

## 9. Known limitations

- Supported domain is intentionally small; extending it means adding grammar + domain construction + tests.
- Numeric features are treated as real-valued; integer-only semantics are a subset (integer counterexamples are still produced at boundaries).
- The optional HTTP client is OpenAI-compatible and unverified against a paid endpoint; the fake client is the reproducible path.
- Cached `INCOMPLETE` reports are stored for audit but re-evaluated by default in tests (`use_cache=False`).
