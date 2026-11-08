import tempfile
from pathlib import Path
import pytest

from autocetacean.ledger import (
    InvalidSlotError,
    LedgerQuotaExceededError,
    PersistentLedger,
)


def test_ledger_initialization():
    ledger = PersistentLedger(allowed_slots=["owner", "self"])
    assert ledger.get_slot("owner") == ""
    assert ledger.get_slot("self") == ""
    assert ledger.revision == 0
    assert ledger.current_total_bytes == 0


def test_ledger_invalid_slot_read():
    ledger = PersistentLedger()
    with pytest.raises(InvalidSlotError):
        ledger.get_slot("unknown_slot")


def test_ledger_invalid_slot_write():
    ledger = PersistentLedger()
    with pytest.raises(InvalidSlotError):
        ledger.update_slot("invalid_slot", "content")


def test_ledger_update_slot_basic():
    ledger = PersistentLedger()
    entry = ledger.update_slot("self", "I am Shen Xun", author="xun")
    assert entry.revision == 1
    assert entry.slot == "self"
    assert entry.content == "I am Shen Xun"
    assert ledger.get_slot("self") == "I am Shen Xun"
    assert ledger.revision == 1


def test_ledger_quota_exceeded():
    ledger = PersistentLedger(max_bytes=20)
    with pytest.raises(LedgerQuotaExceededError):
        ledger.update_slot("self", "This sentence is definitely longer than 20 bytes.")


def test_ledger_quota_cumulative():
    ledger = PersistentLedger(max_bytes=30)
    ledger.update_slot("owner", "1234567890")  # 10 bytes
    ledger.update_slot("self", "1234567890")   # 10 bytes
    assert ledger.current_total_bytes == 20
    with pytest.raises(LedgerQuotaExceededError):
        ledger.update_slot("threads", "123456789012345")  # +15 bytes > 30


def test_ledger_utf8_multibyte_counting():
    ledger = PersistentLedger(max_bytes=20)
    # '沈寻' is 6 bytes in UTF-8
    entry = ledger.update_slot("self", "沈寻")
    assert entry.byte_size == 6
    assert ledger.current_total_bytes == 6


def test_ledger_persistence_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ledger.json"
        l1 = PersistentLedger(storage_path=path)
        l1.update_slot("owner", "Data A")
        l1.update_slot("self", "Data B")

        # Reload in fresh instance
        l2 = PersistentLedger(storage_path=path)
        assert l2.get_slot("owner") == "Data A"
        assert l2.get_slot("self") == "Data B"
        assert l2.revision == 2


def test_ledger_rollback():
    ledger = PersistentLedger()
    ledger.update_slot("self", "Rev 1")
    ledger.update_slot("self", "Rev 2")
    ledger.update_slot("self", "Rev 3")
    assert ledger.get_slot("self") == "Rev 3"

    ok = ledger.rollback_to(2)
    assert ok is True
    assert ledger.get_slot("self") == "Rev 2"
    assert ledger.revision == 2


def test_ledger_rollback_invalid_target():
    ledger = PersistentLedger()
    ledger.update_slot("self", "Initial")
    assert ledger.rollback_to(-1) is False
    assert ledger.rollback_to(99) is False


def test_ledger_export_snapshot():
    ledger = PersistentLedger()
    ledger.update_slot("methods", "Rule 1\nRule 2")
    snap = ledger.export_snapshot()
    assert snap["revision"] == 1
    assert "methods" in snap["slots"]
    assert snap["total_bytes"] > 0
