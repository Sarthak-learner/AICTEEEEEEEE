"""Unit tests for the hash-chained audit log."""
import pytest
from unittest.mock import MagicMock, patch
from app.services.audit import record_event, verify_chain, _canonical
from app.models import AuditEvent


def make_mock_db():
    """Create a minimal mock DB session."""
    events = []

    class MockDB:
        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def first(self):
            return events[-1] if events else None

        def add(self, obj):
            events.append(obj)

        def flush(self):
            if events:
                events[-1].id = len(events)

    return MockDB(), events


class TestAuditHashChain:
    def test_first_event_uses_genesis_hash(self):
        db, events = make_mock_db()
        ev = record_event(db, "TEST_ACTION", actor_id="user1")
        assert ev.prev_hash == "0" * 64
        assert ev.event_hash is not None
        assert len(ev.event_hash) == 64

    def test_canonical_is_stable(self):
        """Same payload always produces same canonical string."""
        payload = {"b": 2, "a": 1, "c": "hello"}
        c1 = _canonical(payload)
        c2 = _canonical(payload)
        assert c1 == c2

    def test_canonical_is_ordered(self):
        """Keys are sorted in canonical form."""
        import json
        payload = {"z": 1, "a": 2}
        canonical = _canonical(payload)
        parsed = json.loads(canonical)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_verify_chain_empty(self):
        """Empty audit log should verify as intact."""
        class EmptyDB:
            def query(self, *a): return self
            def order_by(self, *a): return self
            def all(self): return []
        result = verify_chain(EmptyDB())
        assert result["intact"] is True
        assert result["total_events"] == 0
