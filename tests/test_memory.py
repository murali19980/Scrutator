"""Tests for memory module — including HMAC integrity verification."""

import json
import os
import tempfile
from datetime import datetime

import pytest

from memory.types import KnowledgeMemory, PreferenceMemory
from memory.storage import JSONStorage
from memory.manager import MemoryManager


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

def test_memory_serialization():
    km = KnowledgeMemory(
        id="test_k1",
        topic="solid-state batteries",
        content="Toyota is planning a solid-state EV by 2027.",
        timestamp=datetime(2026, 6, 26, 12, 0, 0),
        confidence=90.0,
        metadata={"link": "https://example.com/toyota"},
    )

    d = km.to_dict()
    assert d["id"] == "test_k1"
    assert d["type"] == "knowledge"
    assert d["topic"] == "solid-state batteries"
    assert d["content"] == "Toyota is planning a solid-state EV by 2027."
    assert d["confidence"] == 90.0
    assert d["metadata"]["link"] == "https://example.com/toyota"

    km_back = KnowledgeMemory.from_dict(d)
    assert km_back.id == "test_k1"
    assert km_back.type == "knowledge"
    assert km_back.topic == "solid-state batteries"
    assert km_back.content == "Toyota is planning a solid-state EV by 2027."
    assert km_back.confidence == 90.0


# ---------------------------------------------------------------------------
# JSONStorage tests (signed format)
# ---------------------------------------------------------------------------

def test_json_storage_save_and_load(monkeypatch):
    """Round-trip: save then load should return the same entries."""
    monkeypatch.setenv("SCRUTATOR_MEMORY_HMAC_KEY", "test-hmac-secret-1234")
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        storage = JSONStorage(store_path)

        pm = PreferenceMemory(
            id="test_p1",
            topic="sources",
            content="Prefer academic papers over news sites.",
            timestamp=datetime.now(),
        )

        storage.save([pm])
        loaded = storage.load()

        assert len(loaded) == 1
        assert loaded[0].id == "test_p1"
        assert loaded[0].type == "preference"
        assert loaded[0].topic == "sources"
        assert loaded[0].content == "Prefer academic papers over news sites."


def test_json_storage_writes_signed_envelope(monkeypatch):
    """Saved file should be a signed envelope dict, not a raw list."""
    monkeypatch.setenv("SCRUTATOR_MEMORY_HMAC_KEY", "test-hmac-secret-1234")
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        storage = JSONStorage(store_path)

        entry = PreferenceMemory(id="e1", topic="test", content="hello", timestamp=datetime.now())
        storage.save([entry])

        with open(store_path) as f:
            raw = json.load(f)

        assert isinstance(raw, dict), "Saved file should be a signed envelope dict"
        assert "data" in raw, "Envelope must contain 'data'"
        assert "sig" in raw, "Envelope must contain 'sig' HMAC signature"
        assert isinstance(raw["data"], list)


def test_json_storage_rejects_tampered_file(monkeypatch):
    """Loading a tampered memory file should raise ValueError."""
    monkeypatch.setenv("SCRUTATOR_MEMORY_HMAC_KEY", "test-hmac-secret-1234")
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        storage = JSONStorage(store_path)

        entry = PreferenceMemory(id="e2", topic="test", content="original", timestamp=datetime.now())
        storage.save([entry])

        # Tamper with the file content directly
        with open(store_path) as f:
            envelope = json.load(f)
        envelope["data"][0]["content"] = "tampered!"
        with open(store_path, "w") as f:
            json.dump(envelope, f)

        with pytest.raises(ValueError, match="integrity check failed"):
            storage.load()


def test_json_storage_loads_legacy_format(monkeypatch):
    """Legacy plain-list format should load without error (with a warning)."""
    monkeypatch.setenv("SCRUTATOR_MEMORY_HMAC_KEY", "test-hmac-secret-1234")
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        legacy_data = [
            {
                "id": "legacy1",
                "type": "preference",
                "topic": "legacy",
                "content": "old format",
                "timestamp": "2026-01-01T00:00:00",
                "confidence": 50.0,
                "metadata": {},
            }
        ]
        with open(store_path, "w") as f:
            json.dump(legacy_data, f)

        storage = JSONStorage(store_path)
        import warnings
        with warnings.catch_warnings(record=True):
            entries = storage.load()
        assert len(entries) == 1
        assert entries[0].id == "legacy1"


def test_json_storage_chmod_600(monkeypatch):
    """Saved file should have owner-only permissions (chmod 600) on POSIX systems."""
    monkeypatch.setenv("SCRUTATOR_MEMORY_HMAC_KEY", "test-hmac-secret-1234")
    if os.name == "nt":
        pytest.skip("chmod 600 is not enforced on Windows")
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        storage = JSONStorage(store_path)
        entry = PreferenceMemory(id="e3", topic="test", content="hi", timestamp=datetime.now())
        storage.save([entry])
        mode = oct(os.stat(store_path).st_mode)
        assert mode.endswith("600"), f"Expected 600 permissions, got: {mode}"


# ---------------------------------------------------------------------------
# MemoryManager tests
# ---------------------------------------------------------------------------

def test_memory_manager_keyword_matching(monkeypatch):
    monkeypatch.setenv("SCRUTATOR_MEMORY_HMAC_KEY", "test-hmac-secret-1234")
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        config = {
            "enabled": True,
            "storage_type": "json",
            "storage_path": store_path,
        }
        manager = MemoryManager(config)
        manager.add(
            PreferenceMemory(id="m1", topic="electric vehicles", content="Prefer reading about EV motors.")
        )
        manager.add(
            KnowledgeMemory(id="m2", topic="artificial intelligence", content="LLMs require high GPU memory.")
        )

        results = manager.find("neural networks and artificial intelligence")
        assert len(results) >= 1
        assert results[0].id == "m2"

        results_none = manager.find("baking sourdough bread")
        assert len(results_none) == 0
