"""Tests for memory module."""

import pytest
import os
import tempfile
from datetime import datetime
from memory.types import KnowledgeMemory, PreferenceMemory
from memory.storage import JSONStorage
from memory.manager import MemoryManager

def test_memory_serialization():
    # Test dictionary mapping of types
    km = KnowledgeMemory(
        id="test_k1",
        topic="solid-state batteries",
        content="Toyota is planning a solid-state EV by 2027.",
        timestamp=datetime(2026, 6, 26, 12, 0, 0),
        confidence=90.0,
        metadata={"link": "https://example.com/toyota"}
    )
    
    d = km.to_dict()
    assert d["id"] == "test_k1"
    assert d["type"] == "knowledge"
    assert d["topic"] == "solid-state batteries"
    assert d["content"] == "Toyota is planning a solid-state EV by 2027."
    assert d["confidence"] == 90.0
    assert d["metadata"]["link"] == "https://example.com/toyota"

    # From dict back
    km_back = KnowledgeMemory.from_dict(d)
    assert km_back.id == "test_k1"
    assert km_back.type == "knowledge"
    assert km_back.topic == "solid-state batteries"
    assert km_back.content == "Toyota is planning a solid-state EV by 2027."
    assert km_back.confidence == 90.0

def test_json_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        storage = JSONStorage(store_path)
        
        pm = PreferenceMemory(
            id="test_p1",
            topic="sources",
            content="Prefer academic papers over news sites.",
            timestamp=datetime.now()
        )
        
        storage.save([pm])
        loaded = storage.load()
        
        assert len(loaded) == 1
        assert loaded[0].id == "test_p1"
        assert loaded[0].type == "preference"
        assert loaded[0].topic == "sources"
        assert loaded[0].content == "Prefer academic papers over news sites."

def test_memory_manager_keyword_matching():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "store.json")
        config = {
            "enabled": True,
            "storage_type": "json",
            "storage_path": store_path
        }
        
        manager = MemoryManager(config)
        
        # Add some memories
        manager.add(PreferenceMemory(
            id="m1",
            topic="electric vehicles",
            content="Prefer reading about electric vehicle motors."
        ))
        manager.add(KnowledgeMemory(
            id="m2",
            topic="artificial intelligence",
            content="Large Language Models require high GPU memory."
        ))
        
        # Test finding matching topic
        results = manager.find("neural networks and artificial intelligence")
        assert len(results) >= 1
        assert results[0].id == "m2"
        
        # Test finding unrelated topic
        results_none = manager.find("baking sourdough bread")
        assert len(results_none) == 0
