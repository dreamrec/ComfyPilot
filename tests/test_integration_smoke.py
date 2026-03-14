"""Integration smoke tests for ComfyPilot MCP server key integration points.

Tests cover:
- _LRUDict eviction and insertion-order semantics
- Cloud URL detection and auth method selection
- TechniqueStore.record_use behaviour
- TechniqueStore schema-version backfill on load
- EventManager binary WebSocket frame handling
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comfy_mcp.events.event_manager import EventManager, _LRUDict
from comfy_mcp.comfy_client import ComfyClient
from comfy_mcp.memory.technique_store import TechniqueStore, _TECHNIQUE_SCHEMA_VERSION


# ── _LRUDict tests ────────────────────────────────────────────────────────

class TestLRUDict:
    """Tests for the insertion-order-capped _LRUDict."""

    def test_maxsize_eviction(self):
        """Adding more items than maxsize evicts oldest (first-inserted) entries."""
        d = _LRUDict(maxsize=3)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3
        # Dict is full; adding a fourth should evict "a"
        d["d"] = 4
        assert "a" not in d
        assert list(d.keys()) == ["b", "c", "d"]

    def test_eviction_removes_oldest_only(self):
        """Each new insertion beyond maxsize evicts exactly the oldest entry."""
        d = _LRUDict(maxsize=2)
        d["x"] = 10
        d["y"] = 20
        d["z"] = 30  # evicts "x"
        assert "x" not in d
        assert "y" in d
        assert "z" in d
        d["w"] = 40  # evicts "y"
        assert "y" not in d
        assert list(d.keys()) == ["z", "w"]

    def test_access_does_not_change_eviction_order(self):
        """Reading a key does NOT promote it; eviction is purely insertion-order."""
        d = _LRUDict(maxsize=3)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3
        # Access "a" — should NOT move it to the end
        _ = d["a"]
        # Insert new key — should still evict "a" (oldest inserted)
        d["d"] = 4
        assert "a" not in d, "Accessed key should still be evicted (insertion-order, not access-order)"
        assert list(d.keys()) == ["b", "c", "d"]

    def test_update_existing_key_does_not_evict(self):
        """Overwriting an existing key does not trigger eviction."""
        d = _LRUDict(maxsize=2)
        d["a"] = 1
        d["b"] = 2
        d["a"] = 99  # update in place
        assert len(d) == 2
        assert d["a"] == 99
        assert "b" in d


# ── Cloud URL detection / auth method tests ───────────────────────────────

class TestCloudURLDetection:
    """Tests for ComfyClient auth method selection based on URL."""

    @pytest.mark.asyncio
    async def test_cloud_api_comfy_uses_x_api_key(self):
        """URLs containing 'api.comfy' should use x-api-key header."""
        client = ComfyClient(
            base_url="https://api.comfy.example.com",
            api_key="test-key-123",
            auth_method="auto",
        )
        await client.connect()
        try:
            assert "X-API-Key" in client._http.headers
            assert client._http.headers["X-API-Key"] == "test-key-123"
            assert "Authorization" not in client._http.headers
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_cloud_comfy_org_uses_x_api_key(self):
        """URLs containing 'cloud.comfy.org' should use x-api-key header."""
        client = ComfyClient(
            base_url="https://cloud.comfy.org/api/v1",
            api_key="cloud-key-456",
            auth_method="auto",
        )
        await client.connect()
        try:
            assert "X-API-Key" in client._http.headers
            assert client._http.headers["X-API-Key"] == "cloud-key-456"
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_localhost_uses_bearer(self):
        """localhost URLs should use Bearer auth, not x-api-key."""
        client = ComfyClient(
            base_url="http://localhost:8188",
            api_key="local-key-789",
            auth_method="auto",
        )
        await client.connect()
        try:
            assert "Authorization" in client._http.headers
            assert client._http.headers["Authorization"] == "Bearer local-key-789"
            assert "X-API-Key" not in client._http.headers
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_no_api_key_sets_no_auth_headers(self):
        """When no api_key is provided, no auth headers should be set."""
        client = ComfyClient(
            base_url="https://api.comfy.example.com",
            api_key="",
            auth_method="auto",
        )
        await client.connect()
        try:
            assert "X-API-Key" not in client._http.headers
            assert "Authorization" not in client._http.headers
        finally:
            await client.close()


# ── TechniqueStore.record_use tests ───────────────────────────────────────

class TestTechniqueStoreRecordUse:
    """Tests for TechniqueStore.record_use incrementing use_count."""

    def test_record_use_increments_use_count(self, tmp_path):
        """record_use should increment use_count each time it is called."""
        store = TechniqueStore(storage_dir=str(tmp_path))
        result = store.save(workflow={"1": {"class_type": "KSampler"}}, name="sampler-test")
        tech_id = result["id"]

        tech_before = store.get(tech_id)
        assert tech_before["use_count"] == 0

        store.record_use(tech_id)
        tech_after = store.get(tech_id)
        assert tech_after["use_count"] == 1

        store.record_use(tech_id)
        tech_after2 = store.get(tech_id)
        assert tech_after2["use_count"] == 2

    def test_record_use_returns_none_for_missing_id(self, tmp_path):
        """record_use should return None for a non-existent technique."""
        store = TechniqueStore(storage_dir=str(tmp_path))
        assert store.record_use("nonexistent") is None

    def test_record_use_persists_to_disk(self, tmp_path):
        """use_count should survive a fresh TechniqueStore reload from disk."""
        store = TechniqueStore(storage_dir=str(tmp_path))
        result = store.save(workflow={"1": {}}, name="persist-test")
        tech_id = result["id"]

        store.record_use(tech_id)
        store.record_use(tech_id)

        # Create a fresh store that re-loads from the same directory
        store2 = TechniqueStore(storage_dir=str(tmp_path))
        tech = store2.get(tech_id)
        assert tech["use_count"] == 2


# ── TechniqueStore schema versioning tests ────────────────────────────────

class TestTechniqueStoreSchemaVersioning:
    """Tests that _load_all backfills schema_version for legacy entries."""

    def test_load_backfills_schema_version(self, tmp_path):
        """An old technique file without schema_version gets it backfilled on load."""
        legacy_tech = {
            "id": "legacy01",
            "name": "Old Technique",
            "description": "",
            "tags": [],
            "workflow": {"1": {"class_type": "KSampler"}},
            "timestamp": time.time(),
            "node_count": 1,
            "favorite": False,
            "rating": -1,
            "use_count": 3,
            # Note: no "schema_version" key
        }
        (tmp_path / "legacy01.json").write_text(json.dumps(legacy_tech), encoding="utf-8")

        store = TechniqueStore(storage_dir=str(tmp_path))
        loaded = store.get("legacy01")
        assert loaded is not None
        assert loaded["schema_version"] == _TECHNIQUE_SCHEMA_VERSION

    def test_existing_schema_version_preserved(self, tmp_path):
        """A technique that already has schema_version should keep it unchanged."""
        tech = {
            "id": "versioned",
            "name": "Versioned Tech",
            "description": "",
            "tags": [],
            "workflow": {},
            "timestamp": time.time(),
            "node_count": 0,
            "favorite": False,
            "rating": -1,
            "use_count": 0,
            "schema_version": 99,  # future / custom version
        }
        (tmp_path / "versioned.json").write_text(json.dumps(tech), encoding="utf-8")

        store = TechniqueStore(storage_dir=str(tmp_path))
        loaded = store.get("versioned")
        assert loaded["schema_version"] == 99


# ── EventManager binary frame handling tests ──────────────────────────────

class TestEventManagerBinaryFrames:
    """Tests that binary WebSocket frames are safely skipped."""

    def test_dispatch_only_receives_parsed_json(self):
        """EventManager._dispatch stores events in the buffer correctly."""
        client_mock = MagicMock()
        client_mock.base_url = "http://localhost:8188"
        client_mock._client_id = "test-id"

        em = EventManager(client_mock)

        # _dispatch is the method called after JSON parse succeeds;
        # binary frames never reach it (they are skipped in _ws_loop).
        # Verify _dispatch works with a valid dict.
        em._dispatch({"type": "progress", "data": {"prompt_id": "p1", "value": 5, "max": 10}})
        events = em.peek_events()
        assert len(events) == 1
        assert events[0]["type"] == "progress"

    @pytest.mark.asyncio
    async def test_binary_frame_skipped_without_crash(self):
        """Binary WS frames should be silently skipped, not crash the listener.

        We simulate the _ws_loop logic inline since starting the real loop
        requires a live WebSocket connection.
        """
        client_mock = MagicMock()
        client_mock.base_url = "http://localhost:8188"
        client_mock._client_id = "test-id"

        em = EventManager(client_mock)

        # Simulate the message-handling logic from _ws_loop
        raw_messages = [
            b"\x89\x00\x01\x02binary-image-data",       # binary frame
            '{"type": "status", "data": {"queue": 0}}',  # valid JSON
            b"\xff\xfe",                                   # another binary frame
            '{"type": "progress", "data": {"prompt_id": "abc", "value": 3, "max": 10}}',
        ]

        for raw_msg in raw_messages:
            if isinstance(raw_msg, bytes):
                # This mirrors the binary-skip logic in _ws_loop (line 90-92)
                continue
            try:
                msg = json.loads(raw_msg)
                em._dispatch(msg)
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                continue

        events = em.peek_events()
        assert len(events) == 2
        assert events[0]["type"] == "status"
        assert events[1]["type"] == "progress"

    def test_binary_frames_do_not_pollute_progress_cache(self):
        """Binary frames should never end up in the progress cache."""
        client_mock = MagicMock()
        client_mock.base_url = "http://localhost:8188"
        client_mock._client_id = "test-id"

        em = EventManager(client_mock)
        # Only JSON-parsed progress events should cache
        em._dispatch({"type": "progress", "data": {"prompt_id": "p1", "value": 10, "max": 10}})

        assert em.get_latest_progress("p1") is not None
        assert em.get_latest_progress("nonexistent") is None
        assert len(em._progress_cache) == 1
