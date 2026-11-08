"""Persistent versioned structured memory ledger."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union


class LedgerQuotaExceededError(Exception):
    """Raised when memory update exceeds maximum allowed byte quota."""


class InvalidSlotError(Exception):
    """Raised when an unconfigured or malformed slot is accessed."""


@dataclass
class LedgerEntry:
    """Historical revision of a single slot."""
    revision: int
    slot: str
    content: str
    byte_size: int
    timestamp: float = field(default_factory=time.time)
    author: str = "agent"


class PersistentLedger:
    """Thread-safe, atomic versioned memory store with quota enforcement."""

    DEFAULT_MAX_BYTES = 10_752  # Standard 10.5 KB global quota

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        allowed_slots: Optional[List[str]] = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self.max_bytes = max_bytes
        self.allowed_slots: Set[str] = set(
            allowed_slots or ["owner", "self", "threads", "slang", "methods"]
        )
        self._slots: Dict[str, str] = {slot: "" for slot in self.allowed_slots}
        self._history: List[LedgerEntry] = []
        self._revision = 0

        if self.storage_path and self.storage_path.exists():
            self._load_from_disk()

    @property
    def current_total_bytes(self) -> int:
        return sum(len(content.encode("utf-8")) for content in self._slots.values())

    @property
    def revision(self) -> int:
        return self._revision

    def get_slot(self, slot: str) -> str:
        if slot not in self.allowed_slots:
            raise InvalidSlotError(f"Slot {slot!r} is not allowed: {sorted(self.allowed_slots)}")
        return self._slots.get(slot, "")

    def update_slot(self, slot: str, content: str, author: str = "agent") -> LedgerEntry:
        if slot not in self.allowed_slots:
            raise InvalidSlotError(f"Slot {slot!r} is not allowed: {sorted(self.allowed_slots)}")

        clean_content = content.strip()
        new_slot_bytes = len(clean_content.encode("utf-8"))
        other_slots_bytes = sum(
            len(c.encode("utf-8")) for s, c in self._slots.items() if s != slot
        )

        projected_total = other_slots_bytes + new_slot_bytes
        if projected_total > self.max_bytes:
            raise LedgerQuotaExceededError(
                f"Update rejected: projected size {projected_total}B exceeds max quota {self.max_bytes}B"
            )

        self._slots[slot] = clean_content
        self._revision += 1

        entry = LedgerEntry(
            revision=self._revision,
            slot=slot,
            content=clean_content,
            byte_size=new_slot_bytes,
            author=author,
        )
        self._history.append(entry)

        if self.storage_path:
            self._save_to_disk()

        return entry

    def export_snapshot(self) -> Dict[str, Any]:
        return {
            "revision": self._revision,
            "total_bytes": self.current_total_bytes,
            "max_bytes": self.max_bytes,
            "slots": dict(self._slots),
        }

    def rollback_to(self, target_revision: int) -> bool:
        if target_revision < 0 or target_revision > self._revision:
            return False

        reconstructed: Dict[str, str] = {slot: "" for slot in self.allowed_slots}
        for entry in self._history:
            if entry.revision <= target_revision:
                reconstructed[entry.slot] = entry.content

        self._slots = reconstructed
        self._revision = target_revision
        if self.storage_path:
            self._save_to_disk()
        return True

    def _save_to_disk(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(".tmp")
        payload = {
            "revision": self._revision,
            "slots": self._slots,
            "history": [
                {
                    "revision": h.revision,
                    "slot": h.slot,
                    "content": h.content,
                    "byte_size": h.byte_size,
                    "timestamp": h.timestamp,
                    "author": h.author,
                }
                for h in self._history
            ],
        }
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.storage_path)

    def _load_from_disk(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._revision = data.get("revision", 0)
            slots_data = data.get("slots", {})
            for k, v in slots_data.items():
                if k in self.allowed_slots:
                    self._slots[k] = v
            hist_data = data.get("history", [])
            self._history = [
                LedgerEntry(
                    revision=h["revision"],
                    slot=h["slot"],
                    content=h["content"],
                    byte_size=h["byte_size"],
                    timestamp=h.get("timestamp", 0.0),
                    author=h.get("author", "system"),
                )
                for h in hist_data
            ]
        except (json.JSONDecodeError, KeyError, OSError):
            pass
