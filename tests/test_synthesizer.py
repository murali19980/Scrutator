"""Tests for synthesizer module."""

import pytest
from unittest.mock import MagicMock
from core.synthesizer import Synthesizer
from core.model_provider import ModelProvider

def test_synthesize_success():
    mock_provider = MagicMock(spec=ModelProvider)
    llm_output = """
    Summary:
    This is the executive summary paragraph 1.
    This is the executive summary paragraph 2.

    Key Insights:
    - Insight 1: Electric vehicles are growing.
    - Insight 2: Charging infrastructure is a major gap.

    Detailed Synthesis:
    This is the detailed synthesis section.
    """
    mock_provider.generate.return_value = llm_output
    synthesizer = Synthesizer(model_provider=mock_provider)
    
    sources = [
        {"url": "https://example.com/1", "title": "Source 1", "text": "EV sales are up 50% this year."},
        {"url": "https://example.com/2", "title": "Source 2", "text": "We need more chargers."}
    ]
    
    result = synthesizer.synthesize(sources, "electric vehicle growth")
    
    assert "executive summary" in result["summary"]
    assert len(result["key_insights"]) == 2
    assert "Electric vehicles are growing." in result["key_insights"][0]
    assert "detailed synthesis section." in result["detailed_synthesis"]
    mock_provider.generate.assert_called_once()
