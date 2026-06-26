"""Global search engine integration with SearXNG and fallbacks."""

import httpx
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

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
        If unavailable, fallback to public search engines.
        """
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
        """Fallback to DuckDuckGo HTML scraping if SearXNG is unavailable."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        url = "https://html.duckduckgo.com/html/"
        data = {"q": query}
        try:
            # We must use requests or httpx.post
            response = httpx.post(url, data=data, headers=headers, timeout=self.timeout)
            if response.status_code != 200:
                logger.warning(f"DuckDuckGo HTML fallback returned status code {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            
            # DuckDuckGo HTML layout uses 'a.result__url' or 'a.result__snippet'
            links = soup.find_all("a", class_="result__url")
            snippets = soup.find_all("a", class_="result__snippet")
            titles = soup.find_all("a", class_="result__snippet") # wait, title is usually result__title
            # Let's inspect result items:
            result_elements = soup.find_all("div", class_="result")
            for elem in result_elements:
                title_elem = elem.find("a", class_="result__snip") or elem.find("a", class_="result__title")
                url_elem = elem.find("a", class_="result__url")
                snippet_elem = elem.find("a", class_="result__snippet")
                
                if url_elem and title_elem:
                    url_str = url_elem.get("href", "").strip()
                    # Strip DuckDuckGo redirect if present, e.g., //duckduckgo.com/l/?uddg=URL
                    if "uddg=" in url_str:
                        from urllib.parse import parse_qs, urlparse
                        parsed = urlparse(url_str)
                        queries = parse_qs(parsed.query)
                        if "uddg" in queries:
                            url_str = queries["uddg"][0]
                            
                    results.append({
                        "url": url_str,
                        "title": title_elem.get_text(strip=True),
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "language": language
                    })
                    
                if len(results) >= count:
                    break
                    
            logger.info(f"DuckDuckGo fallback returned {len(results)} results.")
            return results
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []
