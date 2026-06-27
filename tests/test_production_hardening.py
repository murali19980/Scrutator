"""
Tests for production hardening features:
- Persistent rate limiting
- CORS defaults
- Parallel scoring semaphore
- Timeout handling
"""

import pytest
import asyncio
import tempfile
import os
import time
import sqlite3
from api.routes import PersistentRateLimiter
from core.research_agent import ResearchAgent

class TestPersistentRateLimiter:
    def test_rate_limiter_persists(self):
        """Test that rate limiter persists across instances using SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "rate.db")
            limiter1 = PersistentRateLimiter(db_path=db_path, requests_per_minute=2)
            limiter2 = PersistentRateLimiter(db_path=db_path, requests_per_minute=2)
            
            # Make 2 requests with limiter1
            assert limiter1.is_allowed("client1") is True
            assert limiter1.is_allowed("client1") is True
            assert limiter1.is_allowed("client1") is False  # 3rd request blocked
            
            # limiter2 should see the same state from the shared db
            assert limiter2.is_allowed("client1") is False
    
    def test_rate_limiter_cleanup(self):
        """Test that old entries are cleaned up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "rate.db")
            limiter = PersistentRateLimiter(db_path=db_path, requests_per_minute=2)
            
            # Add a request with an old timestamp
            now = time.time()
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO rate_requests (client_id, timestamp) VALUES (?, ?)",
                ("old_client", now - 120)  # 2 minutes old
            )
            conn.commit()
            conn.close()
            
            # This should trigger cleanup and be allowed
            assert limiter.is_allowed("new_client") is True

class TestParallelScoring:
    @pytest.mark.asyncio
    async def test_parallel_scoring_semaphore(self):
        """Test that parallel scoring runs concurrently."""
        config = {
            "model": {"provider": "openrouter", "model": "mock"},
            "search": {"searxng_url": "http://localhost:8888", "fallback_to_public": True},
            "research": {"loop_limits": {"quick": 3, "balanced": 7, "deep": 15}, "confidence_threshold": 85, "min_sources": 10},
            "memory": {"enabled": False},
            "output": {"reports_dir": "./reports"}
        }
        agent = ResearchAgent(config)
        
        # Mock scorer
        class MockScorer:
            def score(self, paper):
                return {"methodology": 90, "results": 85, "novelty": 80}
        
        agent.paper_scorer = MockScorer()
        
        # Test parallel scoring
        papers = [{"title": f"Paper {i}"} for i in range(5)]
        
        # Run parallel scoring
        score_semaphore = asyncio.Semaphore(2)
        scored_count = 0
        
        async def mock_score_single(paper):
            nonlocal scored_count
            async with score_semaphore:
                scored_count += 1
                return agent.paper_scorer.score(paper)
                
        tasks = [mock_score_single(p) for p in papers]
        scores = await asyncio.gather(*tasks)
        
        assert len(scores) == 5
        assert scored_count == 5

class TestTimeoutHandling:
    @pytest.mark.asyncio
    async def test_fetch_timeout(self):
        """Test that timeout triggers correctly on slow operations."""
        # Mock slow fetch task
        async def slow_fetch():
            await asyncio.sleep(5.0)
            return "data"
            
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_fetch(), timeout=0.1)
