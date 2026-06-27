"""
Tests for full-text analysis and caching improvements.
"""

import pytest
import asyncio
from core.cache import SearchCache
from core.paper_scorer import PaperScorer
from core.model_provider import ModelProvider
from core.searcher_academic import AcademicSearcher

class TestCacheLogic:
    def test_cache_ignores_none(self, tmp_path):
        """Test that cache does not store None results."""
        db_file = tmp_path / "cache1.db"
        cache = SearchCache(str(db_file))
        # Simulate a failed search by passing None
        cache.set("test", "arxiv", None)
        result = cache.get("test", "arxiv")
        assert result is None

    def test_cache_stores_empty_list(self, tmp_path):
        """Test that cache stores empty list results."""
        db_file = tmp_path / "cache2.db"
        cache = SearchCache(str(db_file))
        cache.set("test", "pubmed", [])
        result = cache.get("test", "pubmed")
        assert result == []

class TestFullTextScoring:
    def test_paper_scorer_uses_full_text(self):
        """Test that scorer includes full text in prompt."""
        # Mock model provider that captures the prompt
        class MockModel:
            def __init__(self):
                self.prompt = ""
            
            def generate(self, prompt, **kwargs):
                self.prompt = prompt
                return "Methodology: 80 - Good\nResults: 70 - OK\nNovelty: 90 - High"
        
        mock = MockModel()
        mock_provider = ModelProvider(provider="openrouter", model="mock")
        # Monkey-patch generate
        mock_provider.generate = mock.generate
        
        scorer = PaperScorer(mock_provider)
        paper = {
            "title": "Test Paper",
            "summary": "This is an abstract.",
            "full_text": "This is the full text of the paper. It contains detailed methodology and results.",
            "authors": ["A. Author"],
            "journal": "Test Journal"
        }
        scorer.score(paper)
        # Check that the prompt contains the full text excerpt
        assert "full text" in mock.prompt.lower()
        assert "test paper" in mock.prompt.lower()
