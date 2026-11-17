"""CLI output-format tests: JSON stays the default, text is opt-in."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verdict import cli

ROOT = Path(__file__).resolve().parent.parent
CODE_WRONG = ROOT / "evals" / "frozen" / "cases" / "code_wrong.json"


def test_default_format_is_json(capsys):
    code = cli.main(["--demo", "--no-cache"])
    payload = capsys.readouterr().out
    report = json.loads(payload)  # raises if the default is not valid JSON
    assert code == 0
    assert report["status"] == "PASS"
    assert {"status", "summary", "findings", "coverage", "check_results"} <= report.keys()


def test_text_format_is_human_readable(capsys):
    code = cli.main(["--demo", "--no-cache", "--format", "text"])
    out = capsys.readouterr().out
    assert code == 0
    assert "VERDICT - REVIEW REPORT" in out
    assert "Status : PASS" in out
    assert "COVERAGE" in out
    assert "[PASS] equivalence:code:routes.py" in out
    assert "FINDINGS (0)" in out
    assert "RESULT: PASS" in out
    assert '"status"' not in out  # not raw JSON


def test_text_format_shows_counterexample_and_nonzero_exit(capsys):
    code = cli.main([str(CODE_WRONG), "--no-cache", "--format", "text"])
    out = capsys.readouterr().out
    assert code == 2
    assert "Status : CHANGES_REQUIRED" in out
    assert "[BLOCKER]" in out
    assert "Counterexample:" in out
    assert "expected route: escalation" in out
    assert "actual route  : normal_queue" in out
    assert "waiting_minutes=" in out


def test_out_respects_requested_format(tmp_path, capsys):
    text_path = tmp_path / "nested" / "report.txt"
    code = cli.main(["--demo", "--no-cache", "--format", "text", "--out", str(text_path)])
    assert code == 0
    assert "Wrote PASS text report to" in capsys.readouterr().out
    assert "VERDICT - REVIEW REPORT" in text_path.read_text(encoding="utf-8")

    json_path = tmp_path / "report.json"
    cli.main(["--demo", "--no-cache", "--out", str(json_path)])
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["status"] == "PASS"


def test_library_renderer_matches_cli_output(capsys):
    from verdict.pipeline import review_bundle
    from scripts.make_demo import make_demo_bundle

    report = review_bundle(make_demo_bundle(), use_cache=False)
    cli.main(["--demo", "--no-cache", "--format", "text"])
    assert capsys.readouterr().out.strip() == report.to_text().strip()


def test_invalid_format_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--demo", "--format", "yaml"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
