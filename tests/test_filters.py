"""
Tests for inclusion/exclusion filters.
"""

import pytest
from core.filters import FilterConfig, PaperFilter

class TestPaperFilter:
    def setup_method(self):
        self.papers = [
            {"title": "Quantum computing advances", "year": 2023, "impact_factor": 4.5, "study_design": "review", "summary": "An analysis of quantum algorithms."},
            {"title": "Classical computing", "year": 2020, "impact_factor": 2.0, "study_design": "rct", "summary": "Comparing processors under classical logic."},
            {"title": "AI in healthcare", "year": 2024, "impact_factor": 6.0, "study_design": "meta-analysis", "summary": "Systematic review of deep learning in clinical settings."},
            {"title": "Older paper", "year": 2015, "impact_factor": 1.0, "study_design": "observational", "summary": "Long-term data collection methods."},
        ]
    
    def test_filter_by_year(self):
        config = FilterConfig(min_year=2020, max_year=2023)
        filter_engine = PaperFilter(config)
        filtered = filter_engine.apply(self.papers)
        assert len(filtered) == 2
        years = [p["year"] for p in filtered]
        assert 2020 in years
        assert 2023 in years
    
    def test_filter_by_impact(self):
        config = FilterConfig(min_impact_factor=3.0)
        filter_engine = PaperFilter(config)
        filtered = filter_engine.apply(self.papers)
        assert len(filtered) == 2  # 4.5 and 6.0
        impacts = [p["impact_factor"] for p in filtered]
        assert 4.5 in impacts
        assert 6.0 in impacts
    
    def test_filter_by_study_design(self):
        config = FilterConfig(allowed_study_designs=["review", "meta-analysis"])
        filter_engine = PaperFilter(config)
        filtered = filter_engine.apply(self.papers)
        assert len(filtered) == 2
        designs = [p["study_design"] for p in filtered]
        assert "review" in designs
        assert "meta-analysis" in designs
    
    def test_filter_by_keywords(self):
        config = FilterConfig(include_keywords=["quantum", "AI"])
        filter_engine = PaperFilter(config)
        filtered = filter_engine.apply(self.papers)
        assert len(filtered) == 2  # Quantum and AI
    
    def test_filter_by_exclude_keywords(self):
        config = FilterConfig(exclude_keywords=["classical"])
        filter_engine = PaperFilter(config)
        filtered = filter_engine.apply(self.papers)
        assert len(filtered) == 3  # All except the classical paper
        titles = [p["title"] for p in filtered]
        assert "Classical computing" not in titles
