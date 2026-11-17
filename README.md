# Verdict

**Evidence-backed AI-assisted review of written requirements, structured specifications, decision workflows and linked Python code.**

Verdict decides whether a ticket-routing implementation actually follows its written policy. It does not trust matching rule IDs, numeric substrings or a model's opinion. Instead it compiles *every artifact* into one decision program and proves behavioural equivalence over a finite domain that is **complete for the supported language**, emitting a concrete ticket when they disagree.

| | |
|---|---|
| Status vocabulary | `PASS` · `CHANGES_REQUIRED` · `INCOMPLETE` |
| Evaluation | 18/18 frozen cases correct (v0 naive baseline: 10/18) |
| Deterministic domain | 27–45 representative inputs per case (exhaustive) |
| Tests | 54 passing |
| Runtime | CPU only, no training, no paid service, no UI |

---

## Quickstart

```powershell
# Python 3.10+ (developed on 3.12.6)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run the built-in synthetic demo -> full JSON report on stdout
python -m verdict --demo

# Run a single synthetic case and save the report
python scripts/capture_case.py pass reports/pass.json

# Run the frozen evaluation (generates the frozen set on first run)
python scripts/run_eval.py

# Controlled ablation: disable exhaustive equivalence
python scripts/run_eval.py --ablate

# Full test suite
python -m pytest
```

CLI flags: `--scenario {valid_clean,valid_finding,truncated,malformed,invented_ref,conflicting,injection,overclaim,timeout}`, `--ablate`, `--require-model`, `--execute-code`, `--no-cache`, `--out <path>`.

---

## How it works

```
 written requirements ──parse──┐
 approval records ──apply──────┼──> effective requirements ──┐
 structured spec ──────────────┼──────────────────────────────┤
 workflow graph ──reachable────┼──────────────────────────────┼──> DecisionProgram (one format)
 linked Python ──AST inspect───┘──────────────────────────────┘
                                                               │
                                       exhaustive boundary domain (complete)
                                                               │
                                       compare oracle vs spec / workflow / code
                                                               │
                                       evidence + counterexample ──> JSON report
                                                               │
                                       model client (fake or optional HTTP) ──> validated annotations
```

1. **Stage 1** — anchored schemas, documented source grammar, restricted Python AST subset, approval engine that only trusts top-level metadata and refuses contradictory approvals.
2. **Stage 2** — deterministic compilation of all four artifacts and exhaustive equivalence checking.
3. **Stage 3** — model-client interface with a deterministic fake and an optional HTTP client, strict validation gate, failure handling, provenance, content-addressed cache.
4. **Stage 4** — frozen evaluation, preserved v0 baseline, two real debug cycles, one controlled ablation.

See [DESIGN.md](DESIGN.md) for the reasoning, [CONTRACTS.md](CONTRACTS.md) for the exact supported language and schemas, and [EVALUATION.md](EVALUATION.md) for measured results.

---

## Example finding

```json
{
  "id": "SEMANTIC_MISMATCH:code:routes.py:CHANGED_THRESHOLD:escalation->normal_queue",
  "severity": "blocker",
  "kind": "CHANGED_THRESHOLD",
  "rule_ref": "requirement:REQ-3",
  "artifact": "code:routes.py",
  "version": "c5",
  "location": "compiled decision paths",
  "evidence": ["ticket.category='billing'", "ticket.urgent=False",
               "ticket.waiting_minutes=31.0", "expected rule: requirement:REQ-3",
               "observed rule: code:routes.py:route_ticket:rule3",
               "3/27 partitions disagree"],
  "message": "code:routes.py routes ticket(...) expected='escalation'.",
  "correction": "Align code:routes.py with the effective requirement ...",
  "expected_route": "escalation",
  "actual_route": "normal_queue",
  "counterexample": {"category": "billing", "urgent": false, "waiting_minutes": 31.0}
}
```

---

## Status semantics

- **`CHANGES_REQUIRED`** — at least one evidenced blocker exists. Unreviewed scope is still disclosed in `coverage.unreviewed`.
- **`INCOMPLETE`** — no blocker established, but evidence is missing, an unsupported construct was found, or a required model check failed. The report says exactly what was not reviewed.
- **`PASS`** — all effective requirements were reviewed exhaustively within the supported scope and no blocker was found.

A failed required check is never converted to `PASS`. Oversized input is reported, never silently truncated.

---

## Honest scope limits

Verdict proves equivalence **only for the documented supported language**: categorical/bool/numeric features with the listed comparison operators, nested AND/OR/NOT, acyclic workflows and the restricted Python subset. It does **not** claim to verify arbitrary prose, arbitrary Python, code execution by default, or real-model performance. Synthetic model responses are provenance, not evidence of real-model quality. See [AI_DISCLOSURE.md](AI_DISCLOSURE.md).

---

## Repository map

```
verdict/              application package
  models.py           Stage 1 schemas + finding/report contracts
  patterns.py         source-language parser
  python_subset.py    AST allow-list inspector
  approvals.py        revision scope + approval authority
  compilers.py        four artifacts -> DecisionProgram
  programs.py         decision-program semantics, units
  semantics.py        exhaustive boundary-partition equivalence
  review.py           Stage 2 orchestration, status logic
  model_client.py     interface, fake, optional HTTP client
  validation.py       model-report validation gate
  cache.py            content-addressed cache
  pipeline.py         end-to-end orchestration
  cli.py              CLI
scripts/              synthetic data, evaluation harness, case capture
evals/frozen/         18 frozen cases + SHA-256 manifest + results
checkpoints/baseline/ preserved v0 naive reviewer
debug/                two real fault-injection / fix cycles
tests/                54 tests
```

Reproducible environment: Python 3.12.6, `pydantic==2.12.5`, `pytest==8.3.3`, `pytest-cov==5.0.0`. CPU only.
