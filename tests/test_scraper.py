"""Tests for scraper module."""

import pytest
import requests_mock
from core.scraper import ContentExtractor

def test_scraper_fallback_success():
    extractor = ContentExtractor(fallback=True)
    
    url = "https://example.com/article"
    html_content = """
    <html>
        <head><title>Test Article Title</title></head>
        <body>
            <header>Header to ignore</header>
            <nav>Navigation to ignore</nav>
            <main>
                <h1>Main Heading</h1>
                <p>This is the first paragraph that contains article content.</p>
                <p>This is the second paragraph which is also content.</p>
            </main>
            <footer>Footer to ignore</footer>
        </body>
    </html>
    """
    
    with requests_mock.Mocker() as m:
        m.get(url, text=html_content)
        result = extractor.extract(url)
        
        assert result is not None
        assert result["url"] == url
        assert result["title"] == "Test Article Title"
        assert "first paragraph" in result["text"]
        assert "second paragraph" in result["text"]
        assert "Header to ignore" not in result["text"]
        assert "Navigation to ignore" not in result["text"]

def test_scraper_fallback_failure():
    extractor = ContentExtractor(fallback=True)
    url = "https://example.com/broken"
    
    with requests_mock.Mocker() as m:
        m.get(url, status_code=404)
        result = extractor.extract(url)
        assert result is None
