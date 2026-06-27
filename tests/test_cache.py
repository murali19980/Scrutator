"""
Unit tests for SQLite SearchCache.
"""

import pytest
import time
from core.cache import SearchCache

def test_cache_set_and_get(tmp_path):
    db_file = tmp_path / "test_cache.db"
    cache = SearchCache(db_path=str(db_file), ttl_days=1)
    
    results = [{"title": "Cached Paper", "doi": "10.1000/xyz123"}]
    
    # Cache miss
    assert cache.get("quantum computing", "arxiv") is None
    
    # Cache set and hit
    cache.set("quantum computing", "arxiv", results)
    cached = cache.get("quantum computing", "arxiv")
    assert cached == results
    
    # Different query is a miss
    assert cache.get("different query", "arxiv") is None

def test_cache_expiry(tmp_path):
    db_file = tmp_path / "test_cache_expiry.db"
    # Set TTL to 0 to force expiration
    cache = SearchCache(db_path=str(db_file), ttl_days=0)
    
    results = [{"title": "Expired Paper"}]
    cache.set("expired query", "pubmed", results)
    
    assert cache.get("expired query", "pubmed") is None

def test_clear_all(tmp_path):
    db_file = tmp_path / "test_cache_clear.db"
    cache = SearchCache(db_path=str(db_file))
    
    cache.set("q1", "arxiv", [{"title": "P1"}])
    cache.set("q2", "pubmed", [{"title": "P2"}])
    
    assert cache.get("q1", "arxiv") is not None
    
    cache.clear_all()
    assert cache.get("q1", "arxiv") is None
    assert cache.get("q2", "pubmed") is None
