"""Web content extraction with Crawl4AI and fallback."""

import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Try to import Crawl4AI with graceful degradation
try:
    from crawl4ai import WebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    logger.warning("Crawl4AI not available; using fallback scraper.")

class ContentExtractor:
    def __init__(self, fallback: bool = True):
        self.fallback = fallback
        self.crawler = None
        if CRAWL4AI_AVAILABLE:
            try:
                self.crawler = WebCrawler()
            except Exception as e:
                logger.warning(f"Crawl4AI initialization failed: {e}")
                self.crawler = None

    def extract(self, url: str) -> Optional[Dict]:
        """Extract clean content from a URL."""
        # Primary: Crawl4AI
        if self.crawler:
            try:
                result = self.crawler.run(url=url)
                if result and result.markdown:
                    return {
                        "url": url,
                        "text": result.markdown,
                        "title": result.title or "",
                        "language": None  # Will be auto-detected later
                    }
            except Exception as e:
                logger.warning(f"Crawl4AI failed for {url}: {e}")

        # Fallback: requests + BeautifulSoup
        if self.fallback:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                resp = requests.get(url, timeout=10, headers=headers)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Remove scripts, styles, ads, nav, footers
                for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'noscript', 'iframe', 'header']):
                    tag.decompose()
                    
                # Take all paragraphs or block sections
                paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li'])
                if not paragraphs:
                    text = soup.get_text(separator='\n', strip=True)
                else:
                    text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
                
                title = soup.title.string.strip() if soup.title else ""
                
                # If content is too short, try getting plain text directly
                if len(text) < 200:
                    text = soup.get_text(separator='\n', strip=True)
                    
                return {
                    "url": url,
                    "text": text,
                    "title": title,
                    "language": None
                }
            except Exception as e:
                logger.warning(f"Fallback extraction failed for {url}: {e}")

        return None
