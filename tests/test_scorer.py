"""Tests for scorer module."""

import pytest
from unittest.mock import MagicMock
from core.scorer import ConfidenceScorer
from core.model_provider import ModelProvider

def test_score_finding_success():
    mock_provider = MagicMock(spec=ModelProvider)
    mock_provider.generate.return_value = "Score: 85\nJustification: Multiple reputable sources support this finding."
    scorer = ConfidenceScorer(model_provider=mock_provider)
    
    finding = "Solid-state batteries show double energy density."
    sources = [
        {"title": "Battery Journal", "url": "https://example.com/bj"},
        {"title": "Tech Report", "url": "https://example.com/tr"}
    ]
    
    result = scorer.score_finding(finding, sources)
    
    assert result["score"] == 85
    assert "Multiple reputable sources" in result["justification"]
    mock_provider.generate.assert_called_once()
