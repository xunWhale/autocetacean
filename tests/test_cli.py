import json
import tempfile
from pathlib import Path
import pytest

from autocetacean.cli import main
from autocetacean.ledger import PersistentLedger


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "autocetacean" in captured.out


def test_cli_ledger_missing_file(capsys):
    ret = main(["ledger", "/path/to/nonexistent_file.json"])
    assert ret == 2
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_cli_ledger_human_output(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "ledger.json"
        l = PersistentLedger(storage_path=p)
        l.update_slot("owner", "Boss")

        ret = main(["ledger", str(p)])
        assert ret == 0
        captured = capsys.readouterr()
        assert "AutoCetacean Ledger Revision 1" in captured.out


def test_cli_ledger_json_output(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "ledger.json"
        l = PersistentLedger(storage_path=p)
        l.update_slot("self", "Whale")

        ret = main(["ledger", str(p), "--json"])
        assert ret == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["revision"] == 1
        assert data["slots"]["self"] == "Whale"
