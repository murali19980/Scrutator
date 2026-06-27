"""
Tests for token usage tracking and Web UI theme setups.
"""

import pytest
import os
import tempfile
from core.model_provider import ModelProvider
from core.reporter_academic import AcademicReporter
from api.web_ui import demo

class TestTokenUsageTracking:
    def test_model_provider_tracks_heuristic_usage(self):
        """Test that ModelProvider accumulates characters/4 heuristic tokens."""
        provider = ModelProvider(provider="openai", model="gpt-4o-mini", api_key="test-key")
        provider.total_input_tokens = 0
        provider.total_output_tokens = 0
        
        # Manually track a prompt and response
        provider._track_usage("Hello world", "System prompt", "This is a response text from LLM.")
        
        usage = provider.get_token_usage()
        # Input prompt + system: 11 + 13 = 24 chars -> 6 tokens
        # Output: 33 chars -> 8 tokens
        assert usage["input_tokens"] == 6
        assert usage["output_tokens"] == 8
        assert usage["total_tokens"] == 14

    def test_model_provider_tracks_actual_usage(self):
        """Test that ModelProvider accumulates actual API usage when supplied."""
        provider = ModelProvider(provider="openai", model="gpt-4o-mini", api_key="test-key")
        provider.total_input_tokens = 0
        provider.total_output_tokens = 0
        
        actual_usage = {
            "prompt_tokens": 15,
            "completion_tokens": 25
        }
        provider._track_usage("Some prompt", "Some system", "Some response", actual_usage)
        
        usage = provider.get_token_usage()
        assert usage["input_tokens"] == 15
        assert usage["output_tokens"] == 25
        assert usage["total_tokens"] == 40

    def test_reporter_includes_token_usage(self):
        """Test that the reporter renders token usage info if present."""
        reporter = AcademicReporter()
        report_data = {
            "query": "Quantum Machine Learning",
            "papers": [
                {
                    "title": "Quantum Kernels",
                    "authors": ["Alice"],
                    "year": 2023,
                    "doi": "10.1000/xyz123",
                    "source": "arxiv",
                    "summary": "This paper presents quantum kernels."
                }
            ],
            "scores": [
                {
                    "methodology": 85,
                    "results": 90,
                    "novelty": 75
                }
            ],
            "contradictions": [],
            "confidence": 85.0,
            "token_usage": {
                "input_tokens": 1200,
                "output_tokens": 800,
                "total_tokens": 2000
            }
        }
        
        md_report = reporter.generate_markdown(report_data)
        assert "📊 Token Usage" in md_report
        assert "Input Tokens:** 1,200" in md_report
        assert "Output Tokens:** 800" in md_report
        assert "Total Tokens:** 2,000" in md_report

class TestWebUITheme:
    def test_create_ui_does_not_crash(self):
        """Test that UI instantiation finishes without syntax or Gradio config crashes."""
        assert demo is not None
        assert demo.title == "Scrutator Academic"
