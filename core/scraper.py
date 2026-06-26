import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
import ipaddress
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def is_safe_url(url: str) -> bool:
    """Check if a URL is safe to request (prevents SSRF)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    
    # 1. Only allow http and https
    if parsed.scheme not in ("http", "https"):
        return False
    
    # 2. Block any URL that contains an IP address (we'll resolve domains separately)
    #    but also block if the hostname is an IP directly.
    hostname = parsed.hostname
    if not hostname:
        return False
    
    # 3. Resolve domain to IP(s) and check against private ranges
    try:
        ips = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC)
    except socket.gaierror:
        return False  # unresolvable = unsafe
    
    for ip_info in ips:
        ip_str = ip_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        # Block private, loopback, link-local, multicast, and reserved
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
            ip.is_multicast or ip.is_reserved):
            return False
    return True

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
        if not is_safe_url(url):
            logger.warning(f"Blocked unsafe URL: {url}")
            return None
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
