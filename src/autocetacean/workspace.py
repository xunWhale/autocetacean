"""Transactional workspace isolation and gate-verified subprocess guard."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

_IGNORED_DIRS = frozenset({".git", ".autocetacean", "__pycache__"})


class WorkspaceGuardError(RuntimeError):
    """Raised when workspace snapshot or rollback encounters an unrecoverable error."""


@dataclass
class GuardOutcome:
    """Structured result of running an untrusted command inside a guarded workspace."""

    passed: bool
    rolled_back: bool
    timed_out: bool
    workspace: str
    cmd: str | list[str]
    cmd_returncode: int | None
    cmd_stdout: str
    cmd_stderr: str
    gate_cmd: str | list[str] | None = None
    gate_returncode: int | None = None
    gate_stdout: str = ""
    gate_stderr: str = ""
    changes: dict[str, list[str]] = field(
        default_factory=lambda: {"added": [], "modified": [], "deleted": []}
    )
    duration_ms: float = 0.0
    trace_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iter_workspace_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED_DIRS)
        cur_path = Path(current)
        for name in sorted(filenames):
            full = cur_path / name
            files[full.relative_to(root).as_posix()] = full
    return files


def _files_equal(a: Path, b: Path) -> bool:
    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and os.readlink(a) == os.readlink(b)
    if a.stat().st_size != b.stat().st_size:
        return False
    return a.read_bytes() == b.read_bytes()


def _copy_entry(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(os.readlink(src), dst)
    else:
        shutil.copy2(src, dst)


class WorkspaceTransaction:
    """Atomic snapshot-and-rollback transaction over a directory or Git repo."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise WorkspaceGuardError(f"Workspace directory does not exist: {self.workspace}")
        self._backup_dir: Path | None = None
        self._baseline_files: dict[str, Path] = {}
        self._baseline_dirs: set[str] = set()
        self._active = False
        self._closed = False

    def begin(self) -> "WorkspaceTransaction":
        if self._active:
            raise WorkspaceGuardError("Transaction already active")
        backup_root = Path(tempfile.mkdtemp(prefix="autocetacean_ws_"))
        self._backup_dir = backup_root
        self._baseline_files = {}
        self._baseline_dirs = set()
        for current, dirnames, filenames in os.walk(self.workspace, topdown=True, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED_DIRS)
            cur_path = Path(current)
            rel_dir = cur_path.relative_to(self.workspace).as_posix()
            if rel_dir != ".":
                self._baseline_dirs.add(rel_dir)
            for name in sorted(filenames):
                src = cur_path / name
                rel = src.relative_to(self.workspace).as_posix()
                dst = backup_root / rel
                _copy_entry(src, dst)
                self._baseline_files[rel] = dst
        self._active = True
        self._closed = False
        return self

    def diff_summary(self) -> dict[str, list[str]]:
        if not self._active:
            raise WorkspaceGuardError("Transaction has not been started")
        current = _iter_workspace_files(self.workspace)
        base_k, cur_k = set(self._baseline_files), set(current)
        return {
            "added": sorted(cur_k - base_k),
            "modified": sorted(
                r for r in (base_k & cur_k) if not _files_equal(self._baseline_files[r], current[r])
            ),
            "deleted": sorted(base_k - cur_k),
        }

    def rollback(self) -> dict[str, list[str]]:
        if not self._active or self._backup_dir is None:
            raise WorkspaceGuardError("Transaction has not been started")
        changes = self.diff_summary()
        for rel in changes["added"]:
            target = self.workspace / rel
            if target.exists() or target.is_symlink():
                target.unlink()
        for rel in changes["modified"] + changes["deleted"]:
            _copy_entry(self._baseline_files[rel], self.workspace / rel)
        for current, _, _ in os.walk(self.workspace, topdown=False, followlinks=False):
            cur_path = Path(current)
            if cur_path == self.workspace:
                continue
            rel_dir = cur_path.relative_to(self.workspace).as_posix()
            if any(p in _IGNORED_DIRS for p in Path(rel_dir).parts):
                continue
            if rel_dir not in self._baseline_dirs:
                try:
                    cur_path.rmdir()
                except OSError:
                    pass
        self._cleanup()
        return changes

    def commit(self) -> dict[str, list[str]]:
        if not self._active:
            raise WorkspaceGuardError("Transaction has not been started")
        changes = self.diff_summary()
        self._cleanup()
        return changes

    def _cleanup(self) -> None:
        if self._backup_dir is not None and self._backup_dir.exists():
            shutil.rmtree(self._backup_dir, ignore_errors=True)
        self._backup_dir = None
        self._active = False
        self._closed = True

    def __enter__(self) -> "WorkspaceTransaction":
        return self.begin()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._active and not self._closed:
            self.rollback() if exc_type is not None else self.commit()


def _run_subprocess(
    cmd: str | Sequence[str],
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> tuple[int | None, str, str, bool]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=merged_env,
        shell=isinstance(cmd, str),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            proc.kill()
        stdout, stderr = proc.communicate()
        return None, stdout, stderr, True


class SubprocessToolGuard:
    """Executes an agent/tool command in a transactional workspace and enforces a gate."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        timeout: float = 30.0,
        gate_timeout: float = 60.0,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self.gate_timeout = gate_timeout
        self.env = dict(env) if env else None

    def run(
        self,
        cmd: str | Sequence[str],
        *,
        gate_cmd: str | Sequence[str] | None = None,
        trace_out: str | Path | None = None,
    ) -> GuardOutcome:
        import json

        start = time.monotonic()
        tx = WorkspaceTransaction(self.workspace).begin()
        timed_out = False
        cmd_rc: int | None = None
        cmd_out = cmd_err = ""
        gate_rc: int | None = None
        gate_out = gate_err = ""
        rolled_back = passed = False

        try:
            cmd_rc, cmd_out, cmd_err, timed_out = _run_subprocess(
                cmd, self.workspace, timeout=self.timeout, env=self.env
            )
            if not timed_out and cmd_rc == 0:
                if gate_cmd is not None:
                    gate_rc, gate_out, gate_err, gate_to = _run_subprocess(
                        gate_cmd, self.workspace, timeout=self.gate_timeout, env=self.env
                    )
                    if gate_to:
                        timed_out = True
                    passed = (not gate_to) and gate_rc == 0
                else:
                    passed = True
            changes = tx.commit() if passed else tx.rollback()
            rolled_back = not passed
        except Exception:
            if tx._active:
                tx.rollback()
            raise

        duration_ms = round((time.monotonic() - start) * 1000.0, 2)
        trace_str = str(trace_out) if trace_out is not None else None
        outcome = GuardOutcome(
            passed=passed,
            rolled_back=rolled_back,
            timed_out=timed_out,
            workspace=str(self.workspace),
            cmd=cmd if isinstance(cmd, str) else list(cmd),
            cmd_returncode=cmd_rc,
            cmd_stdout=cmd_out,
            cmd_stderr=cmd_err,
            gate_cmd=gate_cmd if isinstance(gate_cmd, (str, type(None))) else list(gate_cmd),
            gate_returncode=gate_rc,
            gate_stdout=gate_out,
            gate_stderr=gate_err,
            changes=changes,
            duration_ms=duration_ms,
            trace_path=trace_str,
        )
        if trace_out is not None:
            tp = Path(trace_out)
            tp.parent.mkdir(parents=True, exist_ok=True)
            tp.write_text(json.dumps(outcome.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return outcome
