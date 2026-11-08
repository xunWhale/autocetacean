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

    def list_checkpoints(self) -> List[Checkpoint]:
        return list(self._checkpoints)

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
