"""
Inclusion/Exclusion Filters for academic papers.

Supports filtering by:
- Publication year
- Journal impact factor
- Study design (RCT, review, meta-analysis)
- Keywords (include/exclude)
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class FilterConfig:
    """Configuration for inclusion/exclusion filters."""
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    min_impact_factor: Optional[float] = None
    allowed_study_designs: List[str] = field(default_factory=list)
    include_keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)

class PaperFilter:
    """Apply inclusion/exclusion filters to a list of papers."""
    
    def __init__(self, config: FilterConfig):
        self.config = config
    
    def apply(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply all filters and return filtered papers."""
        filtered = papers
        
        # Apply each filter sequentially
        if self.config.min_year is not None or self.config.max_year is not None:
            filtered = self._filter_by_year(filtered)
        
        if self.config.min_impact_factor is not None:
            filtered = self._filter_by_impact(filtered)
        
        if self.config.allowed_study_designs:
            filtered = self._filter_by_study_design(filtered)
        
        if self.config.include_keywords:
            filtered = self._filter_by_include_keywords(filtered)
        
        if self.config.exclude_keywords:
            filtered = self._filter_by_exclude_keywords(filtered)
        
        return filtered
    
    def _filter_by_year(self, papers: List[Dict]) -> List[Dict]:
        """Filter by publication year."""
        min_year = self.config.min_year
        max_year = self.config.max_year
        result = []
        for p in papers:
            year = p.get("year")
            # If string year, convert to int
            if isinstance(year, str):
                try:
                    year = int(year)
                except ValueError:
                    year = None
            if year is None:
                continue
            if min_year is not None and year < min_year:
                continue
            if max_year is not None and year > max_year:
                continue
            result.append(p)
        return result
    
    def _filter_by_impact(self, papers: List[Dict]) -> List[Dict]:
        """Filter by minimum journal impact factor."""
        min_impact = self.config.min_impact_factor
        result = []
        for p in papers:
            impact = p.get("impact_factor")
            if isinstance(impact, str):
                try:
                    impact = float(impact)
                except ValueError:
                    impact = 0.0
            if impact is None:
                impact = 0.0
            # If we have no impact data, we keep the paper by default (conservative)
            if impact == 0.0:
                result.append(p)
            elif impact >= min_impact:
                result.append(p)
        return result
    
    def _filter_by_study_design(self, papers: List[Dict]) -> List[Dict]:
        """Filter by allowed study designs."""
        allowed = set(k.lower().strip() for k in self.config.allowed_study_designs if k.strip())
        if not allowed:
            return papers
        result = []
        for p in papers:
            design = p.get("study_design", "").lower().strip()
            if not design:
                # If no design specified, we keep it (conservative)
                result.append(p)
            elif design in allowed:
                result.append(p)
        return result
    
    def _filter_by_include_keywords(self, papers: List[Dict]) -> List[Dict]:
        """Filter to include only papers with specific keywords."""
        include = set(k.lower().strip() for k in self.config.include_keywords if k.strip())
        if not include:
            return papers
        result = []
        for p in papers:
            title = p.get("title", "").lower()
            abstract = p.get("summary", "").lower()
            combined = title + " " + abstract
            found = False
            for keyword in include:
                if keyword in combined:
                    found = True
                    break
            if found:
                result.append(p)
        return result
    
    def _filter_by_exclude_keywords(self, papers: List[Dict]) -> List[Dict]:
        """Exclude papers with specific keywords."""
        exclude = set(k.lower().strip() for k in self.config.exclude_keywords if k.strip())
        if not exclude:
            return papers
        result = []
        for p in papers:
            title = p.get("title", "").lower()
            abstract = p.get("summary", "").lower()
            combined = title + " " + abstract
            should_exclude = False
            for keyword in exclude:
                if keyword in combined:
                    should_exclude = True
                    break
            if not should_exclude:
                result.append(p)
        return result
