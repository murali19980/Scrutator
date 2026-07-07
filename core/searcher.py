"""Global search engine integration with SearXNG and fallbacks."""

import httpx
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Maximum query length to send to any search engine.
# Very long queries cause 400/0-result responses.
MAX_QUERY_LENGTH = 120


def _truncate_query(query: str) -> str:
    """Trim a query to MAX_QUERY_LENGTH characters, ending on a word boundary."""
    if len(query) <= MAX_QUERY_LENGTH:
        return query
    truncated = query[:MAX_QUERY_LENGTH].rsplit(" ", 1)[0]
    logger.info(f"Query truncated from {len(query)} to {len(truncated)} chars for search.")
    return truncated


class SearXNGClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8888",
        timeout: float = 10.0,
        fallback_to_public: bool = True
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.fallback_to_public = fallback_to_public

    def search(self, query: str, language: str = "en", count: int = 10) -> List[Dict]:
        """
        Search using self-hosted SearXNG instance.
        If unavailable, fall back to DuckDuckGo HTML scraping.
        """
        query = _truncate_query(query)

        try:
            results = self._search_searxng(query, language, count)
            if results:
                logger.info(f"SearXNG returned {len(results)} results.")
                return results
        except Exception as e:
            logger.warning(f"SearXNG search failed or unavailable: {e}")

        if self.fallback_to_public:
            logger.info("Falling back to public DuckDuckGo search.")
            return self._search_fallback(query, language, count)
        return []

    def _search_searxng(self, query: str, language: str, count: int) -> List[Dict]:
        """Query SearXNG instance."""
        response = httpx.get(
            f"{self.base_url}/search",
            params={
                "q": query,
                "language": language,
                "format": "json",
                "count": count
            },
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for result in data.get("results", []):
            results.append({
                "url": result.get("url"),
                "title": result.get("title"),
                "snippet": result.get("content", ""),
                "language": language
            })
        return results

    def _search_fallback(self, query: str, language: str, count: int) -> List[Dict]:
        """
        Fallback to DuckDuckGo Lite HTML scraping.

        Uses the lightweight /lite endpoint which has stable, simple HTML
        and doesn't require JavaScript.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            # Use DuckDuckGo Lite — simpler, more stable HTML than html.duckduckgo.com
            response = httpx.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query, "kl": "us-en"},
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )

            if response.status_code != 200:
                logger.warning(f"DuckDuckGo Lite returned status {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            # DDG Lite layout: results are in <table> rows.
            # Odd rows = link, even rows = snippet.
            # Link rows contain an <a> tag with the actual URL.
            # We parse all <a> tags inside result tables.
            result_links = []

            # Try table-based parsing (DDG Lite standard layout)
            for a_tag in soup.find_all("a", class_="result-link"):
                href = a_tag.get("href", "").strip()
                title = a_tag.get_text(strip=True)
                if href and title and href.startswith("http"):
                    result_links.append((href, title))

            # Fallback: any <a> with an external href that isn't DDG navigation
            if not result_links:
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    title = a_tag.get_text(strip=True)
                    if (
                        href.startswith("http")
                        and "duckduckgo.com" not in href
                        and "duck.co" not in href
                        and len(title) > 10
                    ):
                        result_links.append((href, title))

            # Build snippet map from the page text blocks near links
            snippet_cells = [
                td.get_text(strip=True)
                for td in soup.find_all("td", class_="result-snippet")
            ]

            for i, (href, title) in enumerate(result_links[:count]):
                snippet = snippet_cells[i] if i < len(snippet_cells) else ""
                results.append({
                    "url": href,
                    "title": title,
                    "snippet": snippet,
                    "language": language,
                })

            logger.info(f"DuckDuckGo Lite fallback returned {len(results)} results.")
            return results

        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []
