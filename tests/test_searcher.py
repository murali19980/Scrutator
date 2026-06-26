"""Tests for searcher module."""

import pytest
import respx
import httpx
from core.searcher import SearXNGClient

@pytest.fixture
def mock_client():
    return SearXNGClient(base_url="http://mock-searxng:8888", fallback_to_public=True)

@respx.mock
def test_searxng_success(mock_client):
    # Mocking SearXNG response
    respx.get("http://mock-searxng:8888/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/1", "title": "Result 1", "content": "Snippet 1"},
                    {"url": "https://example.com/2", "title": "Result 2", "content": "Snippet 2"}
                ]
            }
        )
    )
    
    results = mock_client.search("test query", language="en", count=2)
    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["title"] == "Result 1"
    assert results[0]["snippet"] == "Snippet 1"
    assert results[0]["language"] == "en"

@respx.mock
def test_searxng_fallback(mock_client):
    # SearXNG fails with 500
    respx.get("http://mock-searxng:8888/search").mock(
        return_value=httpx.Response(500)
    )
    
    # Mocking DuckDuckGo HTML fallback response
    respx.post("https://html.duckduckgo.com/html/").mock(
        return_value=httpx.Response(
            200,
            html="""
            <div class="result">
                <a class="result__title" href="https://example.com/fallback">Fallback Title</a>
                <a class="result__url" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffallback">https://example.com/fallback</a>
                <a class="result__snippet">Fallback Snippet text</a>
            </div>
            """
        )
    )
    
    results = mock_client.search("test query", language="en", count=1)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/fallback"
    assert results[0]["title"] == "Fallback Title"
    assert results[0]["snippet"] == "Fallback Snippet text"
