"""Rolling Checkpoint and Deterministic Replay Engine."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from autocetacean.types import Checkpoint, ExecutionContext


class CheckpointManager:
    """Manages rolling snapshot checkpoints with retention policies."""

    def __init__(
        self,
        storage_dir: Optional[Union[str, Path]] = None,
        max_checkpoints: int = 20,
    ) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.max_checkpoints = max_checkpoints
        self._checkpoints: List[Checkpoint] = []

    def create_checkpoint(
        self,
        context: ExecutionContext,
        node_name: str,
        checkpoint_id: Optional[str] = None,
    ) -> Checkpoint:
        """Create an immutable snapshot of the active context state."""
        cid = checkpoint_id or f"cp_{context.session_id}_{len(context.trajectory)}_{int(time.time() * 1000)}"
        cp = Checkpoint(
            checkpoint_id=cid,
            session_id=context.session_id,
            step_index=len(context.trajectory),
            node_name=node_name,
            state=copy.deepcopy(context.state),
            variables=copy.deepcopy(context.variables),
            used_tokens=context.used_tokens,
            timestamp=time.time(),
        )
        self._checkpoints.append(cp)

        # Evict oldest if exceeding retention cap
        if len(self._checkpoints) > self.max_checkpoints:
            self._checkpoints.pop(0)

        if self.storage_dir:
            self._persist_checkpoint(cp)

        return cp

    def restore_into(self, checkpoint: Checkpoint, context: ExecutionContext) -> None:
        """Restore context state and variables from a checkpoint."""
        context.state = copy.deepcopy(checkpoint.state)
        context.variables = copy.deepcopy(checkpoint.variables)
        context.used_tokens = checkpoint.used_tokens

    def get_latest(self) -> Optional[Checkpoint]:
        return self._checkpoints[-1] if self._checkpoints else None

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Lookup a checkpoint by ID in memory or in storage_dir."""
        for cp in reversed(self._checkpoints):
            if cp.checkpoint_id == checkpoint_id:
                return cp
        if self.storage_dir and self.storage_dir.is_dir():
            direct = self.storage_dir / f"{checkpoint_id}.json"
            if direct.is_file():
                cp = self._load_checkpoint_file(direct)
                if cp is not None and cp.checkpoint_id == checkpoint_id:
                    return cp
            for file_path in sorted(self.storage_dir.glob("*.json")):
                cp = self._load_checkpoint_file(file_path)
                if cp is not None and cp.checkpoint_id == checkpoint_id:
                    return cp
        return None

    def load_from_dir(self, storage_dir: Optional[Union[str, Path]] = None) -> Optional[Checkpoint]:
        """Load persisted checkpoints from disk and return the latest checkpoint."""
        target_dir = Path(storage_dir) if storage_dir is not None else self.storage_dir
        if target_dir is None or not target_dir.is_dir():
            return None
        if storage_dir is not None and self.storage_dir is None:
            self.storage_dir = target_dir

        loaded: List[Checkpoint] = []
        for file_path in sorted(target_dir.glob("*.json")):
            cp = self._load_checkpoint_file(file_path)
            if cp is not None:
                loaded.append(cp)

        if not loaded:
            return None

        loaded.sort(key=lambda c: (c.timestamp, c.step_index, c.checkpoint_id))
        if self.max_checkpoints > 0 and len(loaded) > self.max_checkpoints:
            loaded = loaded[-self.max_checkpoints:]
        self._checkpoints = loaded
        return self.get_latest()

    def list_checkpoints(self) -> List[Checkpoint]:
        return list(self._checkpoints)

    @staticmethod
    def _load_checkpoint_file(file_path: Path) -> Optional[Checkpoint]:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or "checkpoint_id" not in data or "session_id" not in data:
            return None
        return Checkpoint(
            checkpoint_id=str(data["checkpoint_id"]),
            session_id=str(data["session_id"]),
            step_index=int(data.get("step_index", 0)),
            node_name=str(data.get("node_name", "")),
            state=copy.deepcopy(data.get("state", {})),
            variables=copy.deepcopy(data.get("variables", {})),
            used_tokens=int(data.get("used_tokens", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            schema_version=str(data.get("schema_version", "1.0.0")),
        )

    def _persist_checkpoint(self, cp: Checkpoint) -> None:
        if not self.storage_dir:
            return
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.storage_dir / f"{cp.checkpoint_id}.json"
        data = {
            "checkpoint_id": cp.checkpoint_id,
            "session_id": cp.session_id,
            "step_index": cp.step_index,
            "node_name": cp.node_name,
            "state": cp.state,
            "variables": cp.variables,
            "used_tokens": cp.used_tokens,
            "timestamp": cp.timestamp,
            "schema_version": cp.schema_version,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
