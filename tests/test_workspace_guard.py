from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from autocetacean import SubprocessToolGuard, WorkspaceTransaction, cli


def _seed_dir(root: Path) -> None:
    (root / "app.py").write_text("VAL = 42\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "keep.txt").write_text("baseline", encoding="utf-8")


def test_transaction_rollback_restores_all_changes(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed_dir(ws)
    tx = WorkspaceTransaction(ws).begin()
    (ws / "app.py").write_text("VAL = 0\n", encoding="utf-8")
    (ws / "sub" / "keep.txt").unlink()
    (ws / "new_dir").mkdir()
    (ws / "new_dir" / "junk.txt").write_text("garbage", encoding="utf-8")
    assert tx.diff_summary() == {"added": ["new_dir/junk.txt"], "deleted": ["sub/keep.txt"], "modified": ["app.py"]}
    tx.rollback()
    assert (ws / "app.py").read_text(encoding="utf-8") == "VAL = 42\n"
    assert (ws / "sub" / "keep.txt").read_text(encoding="utf-8") == "baseline"
    assert not (ws / "new_dir").exists()


def test_guard_preserves_dirty_git_changes_on_rollback(tmp_path: Path) -> None:
    ws = tmp_path / "gitws"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=ws, check=True)
    (ws / "tracked.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=ws, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=ws, check=True, capture_output=True)
    (ws / "tracked.txt").write_text("dirty-before-agent\n", encoding="utf-8")
    (ws / "untracked.txt").write_text("keep-me\n", encoding="utf-8")

    outcome = SubprocessToolGuard(ws).run(
        [sys.executable, "-c", "from pathlib import Path; Path('tracked.txt').write_text('bad'); Path('untracked.txt').unlink(); Path('extra.txt').write_text('x')"],
        gate_cmd=[sys.executable, "-c", "import sys; sys.exit(1)"],
        trace_out=ws / ".autocetacean" / "traces" / "fail.json",
    )
    assert not outcome.passed and outcome.rolled_back
    assert (ws / "tracked.txt").read_text(encoding="utf-8") == "dirty-before-agent\n"
    assert (ws / "untracked.txt").read_text(encoding="utf-8") == "keep-me\n"
    assert not (ws / "extra.txt").exists()
    assert json.loads((ws / ".autocetacean" / "traces" / "fail.json").read_text())["rolled_back"] is True


def test_guard_timeout_and_gate_pass(tmp_path: Path) -> None:
    ws = tmp_path / "ws2"
    ws.mkdir()
    _seed_dir(ws)
    timed = SubprocessToolGuard(ws, timeout=0.3).run(
        [sys.executable, "-c", "import time; from pathlib import Path; Path('app.py').write_text('bad'); time.sleep(5)"],
    )
    assert timed.timed_out and timed.rolled_back and (ws / "app.py").read_text() == "VAL = 42\n"
    ok = SubprocessToolGuard(ws).run(
        [sys.executable, "-c", "from pathlib import Path; Path('app.py').write_text('VAL = 99\\n')"],
        gate_cmd=[sys.executable, "-c", "import app; assert app.VAL == 99"],
    )
    assert ok.passed and not ok.rolled_back and (ws / "app.py").read_text() == "VAL = 99\n"


def test_cli_guard_end_to_end(tmp_path: Path, capsys) -> None:
    ws = tmp_path / "cli_ws"
    ws.mkdir()
    _seed_dir(ws)
    rc = cli.main([
        "guard", "--workspace", str(ws),
        "--cmd", f"{sys.executable} -c \"from pathlib import Path; Path('app.py').write_text('VAL=0\\n')\"",
        "--gate", f"{sys.executable} -c \"import app; assert app.VAL == 42\"",
        "--json",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and out["rolled_back"] is True and (ws / "app.py").read_text() == "VAL = 42\n"
