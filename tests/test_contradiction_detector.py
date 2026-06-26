"""Tests for contradiction_detector module."""

import pytest
from unittest.mock import MagicMock
from core.contradiction_detector import ContradictionDetector
from core.model_provider import ModelProvider

def test_contradiction_detector_success():
    mock_provider = MagicMock(spec=ModelProvider)
    llm_output = """
    Finding A: Paper 1 claims positive effect.
    Finding B: Paper 2 claims zero effect.
    Conflict: The papers report contradictory outcomes for identical treatments.
    Confidence: 95
    """
    mock_provider.generate.return_value = llm_output
    detector = ContradictionDetector(model_provider=mock_provider)
    
    papers = [
        {"title": "Paper 1", "summary": "Positive outcomes."},
        {"title": "Paper 2", "summary": "Zero outcomes."}
    ]
    
    result = detector.detect(papers)
    
    assert len(result) == 1
    assert result[0]["finding_a"] == "Paper 1 claims positive effect."
    assert result[0]["finding_b"] == "Paper 2 claims zero effect."
    assert "contradictory outcomes" in result[0]["conflict"]
    assert result[0]["confidence"] == "95"
