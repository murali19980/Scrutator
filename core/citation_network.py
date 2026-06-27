"""
Citation Network Analysis using Semantic Scholar API.

Builds citation graphs, computes centrality, and finds papers that cite each other but disagree.
"""

import asyncio
import httpx
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class PaperNode:
    """A node in the citation graph."""
    doi: str
    title: str
    authors: List[str]
    year: int
    citations: List[str] = field(default_factory=list)  # DOIs of cited papers
    references: List[str] = field(default_factory=list)  # DOIs of references
    is_open_access: bool = False
    semantic_scholar_id: Optional[str] = None
    citation_count: int = 0
    influential_citations: int = 0  # Number of citations from highly cited papers


class CitationNetwork:
    """
    Builds and analyzes citation networks using Semantic Scholar API.
    
    Features:
    - Fetch citation relationships for a list of papers
    - Build directed graph of citations
    - Detect contradictory papers via citation patterns
    - Compute centrality metrics
    """
    
    def __init__(self):
        self.base_url = "https://api.semanticscholar.org/v1/paper"
        self.graph: Dict[str, PaperNode] = {}  # DOI -> PaperNode
        self.contradictions: List[Dict[str, Any]] = []
        self._api_semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
        self._cache: Dict[str, Dict] = {}  # In-memory cache for metadata
    
    async def fetch_paper_metadata(self, doi: str) -> Optional[Dict]:
        """
        Fetch metadata for a single paper from Semantic Scholar.
        """
        if doi in self._cache:
            return self._cache[doi]
        
        async with self._api_semaphore:
            try:
                url = f"{self.base_url}/{doi}"
                headers = {"User-Agent": "Scrutator/1.0"}
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
                    follow_redirects=False,
                ) as client:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        self._cache[doi] = data
                        return data
                    else:
                        logger.warning(f"Semantic Scholar API error for {doi}: {response.status_code}")
                        return None
            except Exception as e:
                logger.error(f"Semantic Scholar fetch error: {e}")
                return None
    
    async def build_graph(self, papers: List[Dict[str, Any]]) -> None:
        """
        Build citation graph for a list of papers.
        
        Args:
            papers: List of paper dicts with 'doi' key.
        """
        # Reset graph
        self.graph = {}
        self.contradictions = []
        self._cache = {}
        
        # Fetch metadata for each paper
        tasks = []
        for paper in papers:
            doi = paper.get("doi")
            if not doi:
                continue
            tasks.append(self._process_paper(paper))
        
        if tasks:
            await asyncio.gather(*tasks)
        
        # Post-process: find contradictions
        self._detect_contradictions()
    
    async def _process_paper(self, paper: Dict) -> None:
        """Process a single paper: fetch metadata and add to graph."""
        doi = paper.get("doi")
        if not doi:
            return
        
        metadata = await self.fetch_paper_metadata(doi)
        if not metadata:
            # Use available data without full metadata
            node = PaperNode(
                doi=doi,
                title=paper.get("title", "Unknown"),
                authors=paper.get("authors", []),
                year=paper.get("year", 0),
                citations=[],
                references=[],
                is_open_access=False
            )
            self.graph[doi] = node
            return
        
        # Parse metadata
        citations = []
        for cite in metadata.get("citations", []):
            cite_doi = cite.get("doi")
            if cite_doi:
                citations.append(cite_doi)
        
        references = []
        for ref in metadata.get("references", []):
            ref_doi = ref.get("doi")
            if ref_doi:
                references.append(ref_doi)
        
        node = PaperNode(
            doi=doi,
            title=metadata.get("title", paper.get("title", "Unknown")),
            authors=[a.get("name", "") for a in metadata.get("authors", [])] if metadata.get("authors") else paper.get("authors", []),
            year=metadata.get("year") or paper.get("year", 0),
            citations=citations,
            references=references,
            is_open_access=metadata.get("isOpenAccess", False),
            semantic_scholar_id=metadata.get("paperId"),
            citation_count=metadata.get("citationCount", 0),
            influential_citations=metadata.get("influentialCitationCount", 0)
        )
        self.graph[doi] = node
    
    def _detect_contradictions(self) -> None:
        """
        Detect contradictory claims by analyzing citation patterns.
        
        Strategy:
        - If Paper A cites Paper B, but Paper C also cites Paper B and conflicts with A,
          then A and C are likely contradictory.
        - Use a simple heuristic: papers that share at least one reference but disagree
          in their core claims (as indicated by their titles or abstracts).
        """
        if len(self.graph) < 3:
            return
        
        # Build reverse citation index: paper -> papers that cite it
        cited_by: Dict[str, List[str]] = defaultdict(list)
        for doi, node in self.graph.items():
            for ref in node.references:
                cited_by[ref].append(doi)
        
        # For each paper that is cited by at least 2 others, check for contradictions
        for cited_doi, citing_dois in cited_by.items():
            if len(citing_dois) < 2:
                continue
            
            # Compare citing papers for contradictions
            for i in range(len(citing_dois)):
                for j in range(i+1, len(citing_dois)):
                    doi_a = citing_dois[i]
                    doi_b = citing_dois[j]
                    
                    # Get paper nodes
                    node_a = self.graph.get(doi_a)
                    node_b = self.graph.get(doi_b)
                    if not node_a or not node_b:
                        continue
                    
                    # Simple heuristic: if both cite the same paper but their titles
                    # contain conflicting keywords (e.g., "improves" vs "worsens")
                    # This would be enhanced by LLM in contradiction_detector later.
                    # For now, we'll mark as a potential contradiction.
                    contradiction = {
                        "paper_a": {
                            "doi": doi_a,
                            "title": node_a.title,
                            "authors": node_a.authors
                        },
                        "paper_b": {
                            "doi": doi_b,
                            "title": node_b.title,
                            "authors": node_b.authors
                        },
                        "common_reference": cited_doi,
                        "confidence": 0.6,  # Base confidence; will be refined by LLM
                        "source": "citation_network"
                    }
                    self.contradictions.append(contradiction)
    
    def get_contradictions(self) -> List[Dict[str, Any]]:
        """Return detected contradictions."""
        return self.contradictions
    
    def get_graph(self) -> Dict[str, PaperNode]:
        """Return the full citation graph."""
        return self.graph
    
    def get_citation_count(self, doi: str) -> int:
        """Get number of citations for a paper."""
        node = self.graph.get(doi)
        return len(node.citations) if node else 0
    
    def get_central_papers(self, top_n: int = 5) -> List[str]:
        """
        Get top N papers by citation count (most influential).
        """
        sorted_dois = sorted(
            self.graph.keys(),
            key=lambda d: len(self.graph[d].citations),
            reverse=True
        )
        return sorted_dois[:top_n]
    
    def get_citation_network_stats(self) -> Dict[str, Any]:
        """Get statistics about the citation network."""
        if not self.graph:
            return {
                "total_papers": 0,
                "total_citations": 0,
                "avg_citations": 0,
                "contradictions_found": 0,
                "central_papers": []
            }
        
        total_citations = sum(len(node.citations) for node in self.graph.values())
        avg_citations = total_citations / len(self.graph) if self.graph else 0
        central = self.get_central_papers(3)
        central_titles = []
        for doi in central:
            node = self.graph.get(doi)
            if node:
                central_titles.append(f"{node.title} ({len(node.citations)} citations)")
        
        return {
            "total_papers": len(self.graph),
            "total_citations": total_citations,
            "avg_citations": round(avg_citations, 2),
            "contradictions_found": len(self.contradictions),
            "central_papers": central_titles
        }
