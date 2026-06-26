"""Tests for research agent loop."""

import pytest
import os
import tempfile
import yaml
from unittest.mock import MagicMock, patch
from core.research_agent import ResearchAgent

@pytest.fixture
def temp_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "model": {
                "provider": "openrouter",
                "model": "openrouter/free",
                "temperature": 0.7,
                "max_tokens": 1000
            },
            "search": {
                "searxng_url": "http://mock-searxng:8888",
                "fallback_to_public": True
            },
            "research": {
                "loop_limits": {
                    "quick": 2,
                    "balanced": 3
                },
                "confidence_threshold": 80,
                "min_sources": 2,
                "stop_early": True
            },
            "memory": {
                "enabled": False
            },
            "output": {
                "reports_dir": os.path.join(tmpdir, "reports")
            },
            "translation": {
                "enabled": True
            }
        }
        yield config

@patch("core.research_agent.SearXNGClient")
@patch("core.research_agent.ContentExtractor")
@patch("core.research_agent.ModelProvider")
def test_research_agent_run(mock_provider_cls, mock_scraper_cls, mock_searcher_cls, temp_config):
    # Setup mocks
    mock_searcher = mock_searcher_cls.return_value
    mock_searcher.search.return_value = [
        {"url": "https://example.com/1", "title": "Source 1", "snippet": "Text 1", "language": "en"},
        {"url": "https://example.com/2", "title": "Source 2", "snippet": "Text 2", "language": "en"}
    ]
    
    mock_scraper = mock_scraper_cls.return_value
    mock_scraper.extract.side_effect = lambda url: {
        "url": url,
        "title": "Page title",
        "text": f"Scraped text content for {url}",
        "language": "en"
    }
    
    mock_provider = mock_provider_cls.return_value
    # Set return values for generations (refinement query, synthesis, confidence scoring, followup questions)
    mock_provider.generate.side_effect = [
        # Loop 1 Synthesis (Summary, Key Insights, Detailed Synthesis)
        "Summary:\nResult summary\nKey Insights:\n- Insight 1\n- Insight 2\nDetailed Synthesis:\nDetailed result",
        # Loop 1 Confidence Scoring
        "Score: 85\nJustification: Decent findings.",
        # Loop 1 Refinement Query
        "refined search query for more detail",
        # Loop 2 Synthesis (if loop continues)
        "Summary:\nFinal summary\nKey Insights:\n- Insight 1\n- Insight 2\nDetailed Synthesis:\nDetailed final result",
        # Loop 2 Confidence Scoring
        "Score: 90\nJustification: High confidence.",
        # Follow-up questions
        "1. Followup 1\n2. Followup 2"
    ]
    
    agent = ResearchAgent(temp_config)
    
    # We mock should_stop to terminate loop after 1 run
    with patch("core.research_agent.should_stop", return_value=True) as mock_should_stop:
        report_data = agent.run("solid-state battery tech", languages=["en"], mode="quick")
        
        assert report_data is not None
        assert report_data["query"] == "solid-state battery tech"
        assert report_data["overall_confidence"] == 85.0
        assert len(report_data["sources"]) == 2
        assert os.path.exists(report_data["report_path"])
        
        # Verify calls
        mock_searcher.search.assert_called()
        mock_scraper.extract.assert_any_call("https://example.com/1")
        mock_scraper.extract.assert_any_call("https://example.com/2")
        mock_should_stop.assert_called_once()
