"""Test drain_events does not lose unread events."""
from collections import deque
from unittest.mock import MagicMock

from comfy_mcp.events.event_manager import EventManager


def _make_em():
    """Create EventManager with a mock client (no WS needed for drain tests)."""
    em = EventManager(MagicMock())
    return em


def test_drain_untyped_with_limit_preserves_remaining():
    """drain_events(limit=2) on 5 events should return 2 and keep 3."""
    em = _make_em()
    for i in range(5):
        em._event_buffer.append({"type": "progress", "data": {"i": i}, "timestamp": i})

    drained = em.drain_events(event_type=None, limit=2)
    assert len(drained) == 2
    assert len(em._event_buffer) == 3  # BUG: currently 0


def test_drain_typed_preserves_other_types():
    """drain_events(event_type='a') should not remove type 'b' events."""
    em = _make_em()
    em._event_buffer.append({"type": "a", "data": {}, "timestamp": 0})
    em._event_buffer.append({"type": "b", "data": {}, "timestamp": 1})
    em._event_buffer.append({"type": "a", "data": {}, "timestamp": 2})

    drained = em.drain_events(event_type="a", limit=10)
    assert len(drained) == 2
    assert len(em._event_buffer) == 1
    assert em._event_buffer[0]["type"] == "b"
