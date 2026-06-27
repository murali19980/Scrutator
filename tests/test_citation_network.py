"""
Tests for citation network analysis.
"""

import pytest
import asyncio
from core.citation_network import CitationNetwork, PaperNode

@pytest.mark.asyncio
async def test_citation_network_build():
    """Test building citation network."""
    net = CitationNetwork()
    papers = [
        {"doi": "10.1234/paper1", "title": "Paper 1", "authors": ["A. Author"]},
        {"doi": "10.1234/paper2", "title": "Paper 2", "authors": ["B. Author"]},
    ]
    await net.build_graph(papers)
    # Should have some data even if not fully resolved (fallback)
    assert len(net.graph) > 0

@pytest.mark.asyncio
async def test_citation_network_stats():
    """Test network statistics."""
    net = CitationNetwork()
    # Manually add nodes
    node1 = PaperNode(doi="10.1234/1", title="Paper A", authors=["A"], year=2020)
    node1.citations = ["10.1234/2"]
    node2 = PaperNode(doi="10.1234/2", title="Paper B", authors=["B"], year=2021)
    net.graph["10.1234/1"] = node1
    net.graph["10.1234/2"] = node2
    stats = net.get_citation_network_stats()
    assert stats["total_papers"] == 2
    assert stats["total_citations"] == 1
    assert stats["avg_citations"] == 0.5

@pytest.mark.asyncio
async def test_citation_network_contradictions():
    """Test contradiction detection via citation patterns."""
    net = CitationNetwork()
    # Build a small graph with potential contradiction
    node_a = PaperNode(doi="A", title="Improves X", authors=["A"], year=2020)
    node_a.references = ["C"]
    node_b = PaperNode(doi="B", title="Worsens X", authors=["B"], year=2020)
    node_b.references = ["C"]
    node_c = PaperNode(doi="C", title="C Paper", authors=["C"], year=2019)
    net.graph["A"] = node_a
    net.graph["B"] = node_b
    net.graph["C"] = node_c
    net._detect_contradictions()
    contradictions = net.get_contradictions()
    assert len(contradictions) >= 1
    # Check that the contradiction involves A and B
    found = False
    for c in contradictions:
        if c['paper_a']['doi'] == 'A' and c['paper_b']['doi'] == 'B':
            found = True
            break
    assert found

@pytest.mark.asyncio
async def test_citation_network_central_papers():
    """Test central papers extraction."""
    net = CitationNetwork()
    # Create a graph with different citation counts
    node1 = PaperNode(doi="1", title="Paper 1", authors=["A"], year=2020)
    node1.citations = ["2", "3", "4"]
    node2 = PaperNode(doi="2", title="Paper 2", authors=["B"], year=2021)
    node2.citations = ["3"]
    node3 = PaperNode(doi="3", title="Paper 3", authors=["C"], year=2022)
    net.graph["1"] = node1
    net.graph["2"] = node2
    net.graph["3"] = node3
    central = net.get_central_papers(top_n=2)
    assert len(central) == 2
    # Paper 1 should be first (3 citations)
    assert central[0] == "1"
    # Paper 2 should be second (1 citation)
    assert central[1] == "2"

def test_contradiction_detector_integration():
    """Test that the contradiction detector can integrate citation network."""
    from core.contradiction_detector import ContradictionDetector
    from core.model_provider import ModelProvider
    
    # Mock model provider (no actual API calls)
    mock_provider = ModelProvider(provider="openrouter", model="mock")
    # Monkey-patch generate to return a simple response
    mock_provider.generate = lambda p, **k: "No contradictions detected."
    
    detector = ContradictionDetector(mock_provider)
    # Create a citation network with contradictions
    net = CitationNetwork()
    node_a = PaperNode(doi="A", title="Improves X", authors=["A"], year=2020)
    node_a.references = ["C"]
    node_b = PaperNode(doi="B", title="Worsens X", authors=["B"], year=2020)
    node_b.references = ["C"]
    node_c = PaperNode(doi="C", title="C Paper", authors=["C"], year=2019)
    net.graph["A"] = node_a
    net.graph["B"] = node_b
    net.graph["C"] = node_c
    net._detect_contradictions()
    
    # Integrate with detector
    detector.integrate_citation_network(net)
    assert hasattr(detector, '_contradictions')
    assert len(detector._contradictions) >= 1
