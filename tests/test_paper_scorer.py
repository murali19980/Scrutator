"""Tests for paper_scorer module."""

import pytest
from unittest.mock import MagicMock
from core.paper_scorer import PaperScorer
from core.model_provider import ModelProvider

def test_paper_scorer_success():
    mock_provider = MagicMock(spec=ModelProvider)
    llm_output = """
    Methodology: 85 - Rigorous methodology with good control experiments.
    Results: 90 - Extremely consistent and reproducible.
    Novelty: 75 - Interesting approach, moderate novelty.
    """
    mock_provider.generate.return_value = llm_output
    scorer = PaperScorer(model_provider=mock_provider)
    
    paper = {
        "title": "Quantum Error Correction",
        "summary": "We construct a new surface code family.",
        "authors": ["John Doe"],
        "journal": "Quantum Review"
    }
    
    result = scorer.score(paper)
    
    assert result["methodology"] == 85
    assert result["results"] == 90
    assert result["novelty"] == 75
    assert "Rigorous methodology" in result["justification"]
    assert "Extremely consistent" in result["justification"]
    assert "Interesting approach" in result["justification"]
