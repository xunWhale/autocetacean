from __future__ import annotations

import json
from pathlib import Path

from autocetacean import cli, demo


def test_demo_runs_both_checks_and_reports_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())

    report = demo.run_demo(quiet=True)

    assert report["passed"] is True
    names = [check["name"] for check in report["checks"]]
    assert names == ["workspace_guard_rollback", "mcp_record_and_offline_replay"]

    guard = report["checks"][0]
    assert guard["rolled_back"] is True
    assert guard["passed"] is True
    assert guard["gate_returncode"] == 1
    assert guard["junk_removed"] is True

    mcp = report["checks"][1]
    assert mcp["passed"] is True
    assert mcp["replayed_matched_value"] == "12"
    assert mcp["drift_error_code"] == -32602
    assert mcp["mismatch_count"] == 1

    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_cli_demo_json_exit_code_and_fields(capsys) -> None:
    exit_code = cli.main(["demo", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["passed"] is True
    assert len(payload["checks"]) == 2
    assert payload["checks"][0]["name"] == "workspace_guard_rollback"
    assert payload["checks"][1]["name"] == "mcp_record_and_offline_replay"


def test_demo_human_output_prints_pass_line(capsys) -> None:
    exit_code = cli.main(["demo"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert demo.PASS_LINE in out
    assert "[PASS] workspace_guard_rollback" in out
    assert "[PASS] mcp_record_and_offline_replay" in out
