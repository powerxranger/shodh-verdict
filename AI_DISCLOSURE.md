# AI assistance disclosure

AI tools were used during this assessment, as permitted. This document states exactly what was used and what was verified.

## What AI assisted with

- **Architecture and planning:** brainstorming the four-stage design, the shared `DecisionProgram` compilation target, the boundary-partition equivalence approach, and the status semantics.
- **Scaffolding:** first drafts of the Pydantic schemas, parsers, AST walker, model-client interface, evaluation harness and documentation.
- **Debugging support:** interpreting failing reports and suggesting focused fixes for the two injected faults.

## What was verified independently

- Every module was executed; the CLI produces the documented JSON report.
- **54 pytest tests pass**, including a parser/unit/approval/equivalence/model/cache suite, two regression tests for real injected faults, and all 18 frozen evaluation cases.
- The frozen-set hashes are checked on every evaluation run (`verify_freeze`).
- Before/after reports in `debug/` are actual captured outputs, not generated claims.
- The baseline comparison and ablation tables in `EVALUATION.md` were produced by `scripts/run_eval.py` and saved as JSON.

## What AI did **not** establish

- No claim is made about real-model performance. All reported model behaviour comes from a deterministic `FakeModelClient`. The optional HTTP client is a thin OpenAI-compatible hook that was not exercised against a paid endpoint.
- No arbitrary prose or arbitrary Python is claimed to be verified. Unsupported content is reported as unreviewed and forces `INCOMPLETE`.
- No code was executed from untrusted snippets by default; execution is an explicit opt-in path that was tested separately.

## Material AI assistance summary

Substantial: AI helped design and draft the implementation. The correctness argument, test coverage, evaluation numbers and failure handling were verified by running the application and tests in this repository.
