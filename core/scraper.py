import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
import ipaddress
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def is_ip_safe(ip_str: str) -> bool:
    """Check if an IP string is safe (not in a private/non-routable/reserved subnet)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
        
    # Standard properties check
    if (ip.is_private or ip.is_loopback or ip.is_link_local or 
        ip.is_multicast or ip.is_reserved or ip.is_unspecified):
        return False
        
    # Strict subnet blocks
    if ip.version == 4:
        unsafe_networks = [
            ipaddress.ip_network("0.0.0.0/8"),
            ipaddress.ip_network("100.64.0.0/10"),
            ipaddress.ip_network("192.0.0.0/24"),
            ipaddress.ip_network("192.0.2.0/24"),
            ipaddress.ip_network("198.18.0.0/15"),
            ipaddress.ip_network("198.51.100.0/22"),
            ipaddress.ip_network("203.0.113.0/24"),
            ipaddress.ip_network("240.0.0.0/4"),
        ]
        for net in unsafe_networks:
            if ip in net:
                return False
    elif ip.version == 6:
        unsafe_networks_v6 = [
            ipaddress.ip_network("2001:db8::/32"),
        ]
        for net in unsafe_networks_v6:
            if ip in net:
                return False
                
    return True

from requests.adapters import HTTPAdapter

class SSRFSafeAdapter(HTTPAdapter):
    """Custom requests adapter that pins hostname resolution to prevent DNS rebinding."""
    def send(self, request, **kwargs):
        parsed = urlparse(request.url)
        hostname = parsed.hostname
        if not hostname:
            raise requests.exceptions.RequestException("No hostname in URL")
            
        # Check if hostname is an IP directly
        try:
            ipaddress.ip_address(hostname)
            is_ip = True
            resolved_ip = hostname
        except ValueError:
            is_ip = False
            
        if is_ip:
            if not is_ip_safe(resolved_ip):
                raise requests.exceptions.RequestException(f"SSRF Block: Unsafe IP {resolved_ip}")
        else:
            # Resolve DNS
            try:
                ips = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC)
            except socket.gaierror:
                raise requests.exceptions.RequestException(f"SSRF Block: Could not resolve hostname: {hostname}")
                
            safe_ips = []
            for ip_info in ips:
                ip_str = ip_info[4][0]
                if is_ip_safe(ip_str):
                    safe_ips.append(ip_str)
                else:
                    raise requests.exceptions.RequestException(f"SSRF Block: Unsafe IP {ip_str} resolved for {hostname}")
                    
            if not safe_ips:
                raise requests.exceptions.RequestException(f"SSRF Block: No safe IP resolved for {hostname}")
                
            # Pin connection to the first safe resolved IP
            resolved_ip = safe_ips[0]
            
        # Rewrite request URL using IP address
        netloc = parsed.netloc
        if ":" in resolved_ip and not resolved_ip.startswith("["):
            ip_netloc = f"[{resolved_ip}]"
        else:
            ip_netloc = resolved_ip
            
        if parsed.port:
            ip_netloc = f"{ip_netloc}:{parsed.port}"
            
        request.url = request.url.replace(netloc, ip_netloc, 1)
        
        # Keep Host header and SNI for SSL/TLS verification
        request.headers['Host'] = netloc
        kwargs['server_hostname'] = hostname
        
        return super().send(request, **kwargs)

def get_safe_session() -> requests.Session:
    """Helper to build a requests session hardened against SSRF/DNS rebinding."""
    session = requests.Session()
    adapter = SSRFSafeAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def is_safe_url(url: str) -> bool:
    """Check if a URL is safe to request (prevents SSRF)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    
    # 1. Only allow http and https
    if parsed.scheme not in ("http", "https"):
        return False
    
    hostname = parsed.hostname
    if not hostname:
        return False
        
    try:
        ipaddress.ip_address(hostname)
        return is_ip_safe(hostname)
    except ValueError:
        pass
    
    # Resolve domain to IP(s) and check against safe ranges
    try:
        ips = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC)
    except socket.gaierror:
        return False
    
    for ip_info in ips:
        ip_str = ip_info[4][0]
        if not is_ip_safe(ip_str):
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
                session = get_safe_session()
                resp = session.get(url, timeout=10, headers=headers)
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

def download_and_extract_pdf(pdf_url: str) -> Optional[str]:
    """Download a PDF using the safe session and extract its text content using pypdf."""
    if not is_safe_url(pdf_url):
        logger.warning(f"Blocked unsafe PDF URL: {pdf_url}")
        return None
        
    try:
        session = get_safe_session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        resp = session.get(pdf_url, timeout=20, headers=headers)
        resp.raise_for_status()
        
        import io
        from pypdf import PdfReader
        
        pdf_file = io.BytesIO(resp.content)
        reader = PdfReader(pdf_file)
        text_pages = []
        for i, page in enumerate(reader.pages):
            if i >= 15: # limit page extraction size
                break
            page_text = page.extract_text()
            if page_text:
                text_pages.append(page_text)
                
        if text_pages:
            full_text = "\n\n".join(text_pages)
            return full_text
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
            if i >= 20: # limit to 20 pages
                break
            page_text = page.extract_text()
            if page_text:
                text_pages.append(page_text)
        return "\n\n".join(text_pages) if text_pages else None
    except Exception as e:
        logger.error(f"Failed to read local PDF {pdf_path}: {e}")
        return None
