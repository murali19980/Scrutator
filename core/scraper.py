"""
SSRF-hardened HTTP utilities for Scrutator.

Provides:
- is_ip_safe()        — blocks all private/reserved IPv4 and IPv6 ranges
- is_safe_url()       — resolves hostnames first, validates every returned IP
- SSRFSafeTransport   — httpx sync transport that enforces SSRF rules
- SSRFSafeAsyncTransport — httpx async transport that enforces SSRF rules
- make_safe_client()  — returns a pre-configured sync httpx.Client
- make_safe_async_client() — returns a pre-configured async httpx.AsyncClient
- download_and_extract_pdf() — safe PDF fetcher
- extract_local_pdf() — local PDF text extractor
"""

import ipaddress
import io
import logging
import socket
from typing import Optional, Dict
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IP / URL safety
# ---------------------------------------------------------------------------

BLOCKED_NETWORKS = [
    # IPv4
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    # IPv6
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped IPv6
    ipaddress.ip_network("100::/64"),         # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),    # Documentation
]


def is_ip_safe(ip_str: str) -> bool:
    """Return True only if ip_str is a globally routable, non-private address."""
    try:
        addr = ipaddress.ip_address(ip_str)
        # Unwrap IPv4-mapped IPv6 addresses like ::ffff:192.168.1.1
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        return not any(addr in net for net in BLOCKED_NETWORKS)
    except ValueError:
        return False


def is_safe_url(url: str) -> bool:
    """
    Return True only if:
    1. The scheme is http or https.
    2. Every IP that the hostname resolves to passes is_ip_safe().

    Resolving first prevents DNS-rebinding attacks.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        # Resolve and validate every returned address (IPv4 + IPv6)
        results = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        if not results:
            return False
        for *_, (addr, *_) in results:
            if not is_ip_safe(addr):
                return False
        return True
    except (socket.gaierror, ValueError, OSError):
        return False


# ---------------------------------------------------------------------------
# SSRF-safe httpx transports
# ---------------------------------------------------------------------------

SAFE_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


class SSRFSafeTransport(httpx.HTTPTransport):
    """Synchronous httpx transport that blocks SSRF destinations."""

    def handle_request(self, request):
        if not is_safe_url(str(request.url)):
            raise ValueError(f"SSRF blocked: {request.url}")
        return super().handle_request(request)


class SSRFSafeAsyncTransport(httpx.AsyncHTTPTransport):
    """Asynchronous httpx transport that blocks SSRF destinations."""

    async def handle_async_request(self, request):
        if not is_safe_url(str(request.url)):
            raise ValueError(f"SSRF blocked: {request.url}")
        return await super().handle_async_request(request)


def make_safe_client() -> httpx.Client:
    """Return a sync httpx.Client hardened against SSRF."""
    return httpx.Client(
        transport=SSRFSafeTransport(),
        timeout=SAFE_TIMEOUT,
        follow_redirects=False,
    )


def make_safe_async_client() -> httpx.AsyncClient:
    """Return an async httpx.AsyncClient hardened against SSRF."""
    return httpx.AsyncClient(
        transport=SSRFSafeAsyncTransport(),
        timeout=SAFE_TIMEOUT,
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# Legacy helpers — kept for backwards compatibility
# ---------------------------------------------------------------------------

def get_safe_session():
    """Deprecated: use make_safe_client() instead. Returns a safe httpx.Client."""
    logger.warning("get_safe_session() is deprecated; use make_safe_client() instead.")
    return make_safe_client()


# ---------------------------------------------------------------------------
# Crawl4AI optional import
# ---------------------------------------------------------------------------

try:
    from crawl4ai import WebCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    logger.warning("Crawl4AI not available; using fallback scraper.")


# ---------------------------------------------------------------------------
# ContentExtractor
# ---------------------------------------------------------------------------

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
                        "language": None,
                    }
            except Exception as e:
                logger.warning(f"Crawl4AI failed for {url}: {e}")

        # Fallback: httpx + BeautifulSoup
        if self.fallback:
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/91.0.4472.124 Safari/537.36"
                    )
                }
                with make_safe_client() as client:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")

                for tag in soup(["script", "style", "nav", "footer", "aside",
                                  "noscript", "iframe", "header"]):
                    tag.decompose()

                paragraphs = soup.find_all(["p", "h1", "h2", "h3", "h4", "li"])
                if not paragraphs:
                    text = soup.get_text(separator="\n", strip=True)
                else:
                    text = "\n\n".join(
                        p.get_text(strip=True)
                        for p in paragraphs
                        if len(p.get_text(strip=True)) > 20
                    )

                title = soup.title.string.strip() if soup.title else ""

                if len(text) < 200:
                    text = soup.get_text(separator="\n", strip=True)

                return {"url": url, "text": text, "title": title, "language": None}
            except Exception as e:
                logger.warning(f"Fallback extraction failed for {url}: {e}")

        return None


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def download_and_extract_pdf(pdf_url: str) -> Optional[str]:
    """Download a PDF via the safe httpx client and extract text with pypdf."""
    if not is_safe_url(pdf_url):
        logger.warning(f"Blocked unsafe PDF URL: {pdf_url}")
        return None

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        with httpx.Client(
            transport=SSRFSafeTransport(),
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
            follow_redirects=False,
        ) as client:
            resp = client.get(pdf_url, headers=headers)
            resp.raise_for_status()

        from pypdf import PdfReader

        pdf_file = io.BytesIO(resp.content)
        reader = PdfReader(pdf_file)
        text_pages = []
        for i, page in enumerate(reader.pages):
            if i >= 15:
                break
            page_text = page.extract_text()
            if page_text:
                text_pages.append(page_text)

        if text_pages:
            return "\n\n".join(text_pages)
    except Exception as e:
        logger.warning(f"Failed to download or parse PDF {pdf_url}: {e}")

    return None


def extract_local_pdf(pdf_path: str) -> Optional[str]:
    """Extract text from a local PDF file."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        text_pages = []
        for i, page in enumerate(reader.pages):
            if i >= 20:
                break
            page_text = page.extract_text()
            if page_text:
                text_pages.append(page_text)
        return "\n\n".join(text_pages) if text_pages else None
    except Exception as e:
        logger.error(f"Failed to read local PDF {pdf_path}: {e}")
        return None
