import tempfile
from pathlib import Path
import pytest

from autocetacean.checkpoint import CheckpointManager
from autocetacean.types import ExecutionContext


def test_checkpoint_creation_and_deepcopy():
    mgr = CheckpointManager()
    ctx = ExecutionContext(session_id="s1")
    ctx.state["key"] = [1, 2, 3]

    cp = mgr.create_checkpoint(ctx, node_name="node_a")
    assert cp.session_id == "s1"
    assert cp.node_name == "node_a"
    assert cp.state["key"] == [1, 2, 3]

    # Mutate context state, verify checkpoint remains unaffected
    ctx.state["key"].append(4)
    assert cp.state["key"] == [1, 2, 3]


def test_checkpoint_restore():
    mgr = CheckpointManager()
    ctx = ExecutionContext(session_id="s1")
    ctx.state["val"] = 100
    ctx.variables["var"] = "abc"
    ctx.used_tokens = 50

    cp = mgr.create_checkpoint(ctx, node_name="n1")

    # Modify ctx
    ctx.state["val"] = 999
    ctx.variables["var"] = "xyz"
    ctx.used_tokens = 200

    # Restore
    mgr.restore_into(cp, ctx)
    assert ctx.state["val"] == 100
    assert ctx.variables["var"] == "abc"
    assert ctx.used_tokens == 50


def test_checkpoint_eviction():
    mgr = CheckpointManager(max_checkpoints=2)
    ctx = ExecutionContext(session_id="s1")

    c1 = mgr.create_checkpoint(ctx, "n1", checkpoint_id="c1")
    c2 = mgr.create_checkpoint(ctx, "n2", checkpoint_id="c2")
    c3 = mgr.create_checkpoint(ctx, "n3", checkpoint_id="c3")

    cps = mgr.list_checkpoints()
    assert len(cps) == 2
    assert cps[0].checkpoint_id == "c2"
    assert cps[1].checkpoint_id == "c3"


def test_checkpoint_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir)
        mgr = CheckpointManager(storage_dir=storage)
        ctx = ExecutionContext(session_id="s1")
        ctx.state["status"] = "active"

        cp = mgr.create_checkpoint(ctx, "node_init", checkpoint_id="cp_test")
        file_path = storage / "cp_test.json"
        assert file_path.exists()
        assert "status" in file_path.read_text(encoding="utf-8")
