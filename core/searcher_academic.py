"""Academic search engine for ArXiv, PubMed, and OpenAlex."""

import httpx
import logging
import asyncio
import re
import time
import os
import threading
from typing import List, Dict, Optional
from xml.etree import ElementTree
import yaml
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def sanitize_academic_query(query: str) -> str:
    """Sanitize academic search query.
    
    Allows alphanumeric characters, spaces, quotes, hyphens, wildcards, and parenthesis.
    Strips out control characters and potential parameter injection characters.
    """
    if not query:
        return ""
    # Strip control characters
    query = "".join(ch for ch in query if ord(ch) >= 32)
    # White-list characters
    sanitized = re.sub(r'[^a-zA-Z0-9\s"\'\*\-\(\):]', '', query)
    # Normalise spacing
    sanitized = " ".join(sanitized.split())
    return sanitized

def safe_find_text(element, path, namespaces=None, default="") -> str:
    """Safely find sub-element text and clean it up."""
    if element is None:
        return default
    try:
        node = element.find(path, namespaces) if namespaces else element.find(path)
        if node is not None and node.text:
            return node.text.replace("\n", " ").strip()
    except Exception:
        pass
    return default

class AcademicSearcher:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "academic_sources.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
            
        self.arxiv_base = self.config["databases"]["arxiv"]["base_url"]
        self.pubmed_base = self.config["databases"]["pubmed"]["base_url"]
        self.openalex_base = self.config["databases"]["openalex"]["base_url"]
        
        # Load user email from environment if available, otherwise from config
        self.user_email = os.getenv("USER_EMAIL") or self.config.get("user_email", "default@example.com")
        
        self.rate_limits = self.config.get("rate_limits", {"arxiv": 3.0, "pubmed": 5.0, "openalex": 2.0})
        self.last_request_time = {"arxiv": 0.0, "pubmed": 0.0, "openalex": 0.0}
        self.lock = threading.Lock()
        self.client = httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
            follow_redirects=False,
            headers={"User-Agent": f"Scrutator/0.2.0 (mailto:{self.user_email})"},
        )

    def _wait_for_rate_limit(self, source: str):
        """Enforce thread-safe rate limiting per source."""
        with self.lock:
            min_interval = self.rate_limits.get(source, 3.0)
            elapsed = time.time() - self.last_request_time.get(source, 0.0)
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self.last_request_time[source] = time.time()

    def _safe_request(self, method: str, url: str, source: str, **kwargs) -> httpx.Response:
        """Perform request safely with rate limiting and 429 Retry-After backoff."""
        max_retries = 3
        backoff = 2.0
        
        for attempt in range(max_retries + 1):
            self._wait_for_rate_limit(source)
            try:
                if method.lower() == "get":
                    response = self.client.get(url, **kwargs)
                else:
                    response = self.client.post(url, **kwargs)
                
                # Check for rate limit status
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = backoff ** attempt
                    if retry_after:
                        try:
                            sleep_time = float(retry_after)
                        except ValueError:
                            pass
                    logger.warning(f"Rate limited (429) for {source}. Retrying in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue
                
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries:
                    continue
                logger.error(f"HTTP error during request to {url}: {e}")
                raise
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(backoff ** attempt)
                    continue
                logger.error(f"Request failed to {url}: {e}")
                raise

    def search_arxiv(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search ArXiv using the API."""
        clean_query = sanitize_academic_query(query)
        arxiv_query = f"ti:{clean_query} OR abs:{clean_query}"
        params = {
            "search_query": arxiv_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        response = self._safe_request("get", self.arxiv_base, "arxiv", params=params)
        return self._parse_arxiv(response.text)

    def _parse_arxiv(self, xml_text: str) -> List[Dict]:
        """Parse ArXiv Atom XML response."""
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        try:
            root = ElementTree.fromstring(xml_text)
        except Exception as e:
            logger.error(f"Failed to parse ArXiv XML: {e}")
            return []
            
        entries = root.findall("atom:entry", ns)
        results = []
        for entry in entries:
            try:
                title = safe_find_text(entry, "atom:title", ns, "Untitled")
                summary = safe_find_text(entry, "atom:summary", ns, "")
                
                authors = [a.text.strip() for a in entry.findall("atom:author/atom:name", ns) if a is not None and a.text]
                
                published = safe_find_text(entry, "atom:published", ns, "")
                year = published[:4] if len(published) >= 4 else "n.d."
                
                link = entry.find("atom:link[@rel='alternate']", ns)
                url = link.get("href") if link is not None else ""
                
                # Extract DOI if present
                doi = None
                doi_link = entry.find("atom:link[@title='doi']", ns)
                if doi_link is not None:
                    doi = doi_link.get("href")
                    if doi and doi.startswith("http://dx.doi.org/"):
                        doi = doi.replace("http://dx.doi.org/", "")
                    elif doi and doi.startswith("https://doi.org/"):
                        doi = doi.replace("https://doi.org/", "")
                    
                results.append({
                    "title": title,
                    "summary": summary,
                    "authors": authors,
                    "published": published,
                    "year": year,
                    "url": url,
                    "doi": doi,
                    "source": "arxiv"
                })
            except Exception as e:
                logger.warning(f"Skipped parsing single ArXiv entry due to error: {e}")
                continue
        return results

    def search_pubmed(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search PubMed using NCBI E-utilities."""
        clean_query = sanitize_academic_query(query)
        # 1. Search for IDs
        esearch_url = f"{self.pubmed_base}esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": clean_query,
            "retmax": max_results,
            "retmode": "json",
            "usehistory": "y",
            "email": self.user_email
        }
        search_resp = self._safe_request("get", esearch_url, "pubmed", params=params)
        search_data = search_resp.json()
        ids = search_data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        # 2. Fetch abstracts
        efetch_url = f"{self.pubmed_base}efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
            "email": self.user_email
        }
        fetch_resp = self._safe_request("get", efetch_url, "pubmed", params=params)
        return self._parse_pubmed(fetch_resp.text)

    def _parse_pubmed(self, xml_text: str) -> List[Dict]:
        """Parse PubMed XML robustly without namespace constraints."""
        try:
            root = ElementTree.fromstring(xml_text)
        except Exception as e:
            logger.error(f"Failed to parse PubMed XML: {e}")
            return []
            
        results = []
        for article in root.iter("PubmedArticle"):
            try:
                pmid_elem = article.find(".//PMID")
                pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else ""
                
                art = article.find(".//Article")
                if art is None:
                    continue
                    
                title_elem = art.find("ArticleTitle")
                title = "".join(title_elem.itertext()).strip() if title_elem is not None else "Untitled"
                
                # Fetch abstract paragraphs
                abstract_parts = []
                for at in art.findall(".//Abstract/AbstractText"):
                    label = at.get("Label")
                    text = "".join(at.itertext())
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                abstract = "\n".join(abstract_parts) if abstract_parts else ""
                
                # Authors list
                authors = []
                for author in art.findall(".//AuthorList/Author"):
                    last = author.findtext("LastName") or ""
                    forename = author.findtext("ForeName") or author.findtext("Initials") or ""
                    name = f"{forename} {last}".strip() if last else author.findtext("CollectiveName") or ""
                    if name:
                        authors.append(name)
                        
                # Journal Title & Year
                journal_elem = art.find(".//Journal")
                journal = journal_elem.findtext("Title") if journal_elem is not None else ""
                
                year = "n.d."
                if journal_elem is not None:
                    pd = journal_elem.find(".//PubDate")
                    if pd is not None:
                        year_val = pd.findtext("Year")
                        if year_val:
                            year = year_val
                        else:
                            medline = pd.findtext("MedlineDate")
                            if medline:
                                match = re.search(r"\d{4}", medline)
                                if match:
                                    year = match.group()
                                    
                # DOI lookup
                doi = None
                for eid in art.findall("ELocationID"):
                    if eid.get("EIdType") == "doi":
                        doi = eid.text
                        break
                if not doi:
                    for id_node in article.findall(".//ArticleId"):
                        if id_node.get("IdType") == "doi":
                            doi = id_node.text
                            break
                            
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
                
                results.append({
                    "title": title,
                    "summary": abstract,
                    "authors": authors,
                    "journal": journal,
                    "year": year,
                    "url": url,
                    "doi": doi,
                    "source": "pubmed",
                    "pmid": pmid
                })
            except Exception as e:
                logger.warning(f"Skipped parsing single PubMed article due to error: {e}")
                continue
        return results

    def search_openalex(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search OpenAlex."""
        clean_query = sanitize_academic_query(query)
        params = {
            "search": clean_query,
            "per-page": max_results,
            "sort": "relevance_score"
        }
        headers = {"User-Agent": f"Scrutator/1.0 (mailto:{self.user_email})"}
        response = self._safe_request("get", self.openalex_base, "openalex", params=params, headers=headers)
        data = response.json()
        results = []
        for work in data.get("results", []):
            try:
                authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
                abstract = ""
                inv_index = work.get("abstract_inverted_index")
                if inv_index:
                    try:
                        words = []
                        for word, positions in inv_index.items():
                            for pos in positions:
                                words.append((pos, word))
                        words.sort()
                        abstract = " ".join([w[1] for w in words])
                    except Exception as e:
                        logger.debug(f"Failed to reconstruct abstract: {e}")
                
                doi = work.get("doi")
                if doi and doi.startswith("https://doi.org/"):
                    doi = doi.replace("https://doi.org/", "")
                    
                results.append({
                    "title": work.get("title", "Untitled"),
                    "summary": abstract or work.get("abstract", ""),
                    "authors": [a for a in authors if a],
                    "journal": work.get("primary_location", {}).get("source", {}).get("display_name", "") or "",
                    "year": str(work.get("publication_year", "n.d.")),
                    "doi": doi,
                    "url": work.get("doi") or work.get("id") or "",
                    "source": "openalex",
                    "openalex_id": work.get("id")
                })
            except Exception as e:
                logger.warning(f"Skipped parsing single OpenAlex work due to error: {e}")
                continue
        return results

    def search_all(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search all academic databases and merge results."""
        all_results = []
        try:
            arxiv_results = self.search_arxiv(query, max_results)
            all_results.extend(arxiv_results)
        except Exception as e:
            logger.warning(f"ArXiv search failed: {e}")
        try:
            pubmed_results = self.search_pubmed(query, max_results)
            all_results.extend(pubmed_results)
        except Exception as e:
            logger.warning(f"PubMed search failed: {e}")
        try:
            openalex_results = self.search_openalex(query, max_results)
            all_results.extend(openalex_results)
        except Exception as e:
            logger.warning(f"OpenAlex search failed: {e}")
            
        # Deduplicate by DOI or title
        seen = set()
        unique = []
        for item in all_results:
            doi = item.get("doi")
            title = item.get("title", "").strip().lower()
            key = doi if doi else title
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:max_results]

    async def search_all_async(self, query: str, max_results: int = 50, use_cache: bool = True) -> List[Dict]:
        """Search all databases in parallel and return merged, deduplicated results."""
        from core.cache import SearchCache
        cache = SearchCache()
        
        sources = ["arxiv", "pubmed", "openalex"]
        
        async def search_source_task(source: str):
            if use_cache:
                cached = cache.get(query, source)
                if cached is not None:
                    logger.info(f"Cache hit for academic source '{source}'")
                    return cached
            
            try:
                if source == "arxiv":
                    res = await asyncio.to_thread(self.search_arxiv, query, max_results)
                elif source == "pubmed":
                    res = await asyncio.to_thread(self.search_pubmed, query, max_results)
                elif source == "openalex":
                    res = await asyncio.to_thread(self.search_openalex, query, max_results)
                else:
                    res = None
            except Exception as e:
                logger.error(f"Search for source '{source}' failed: {e}")
                res = None
                
            if res is not None and use_cache:
                cache.set(query, source, res)
            return res or []

        # Run tasks in parallel
        tasks = [search_source_task(src) for src in sources]
        results_lists = await asyncio.gather(*tasks)
        
        # Merge and deduplicate
        all_results = []
        for lst in results_lists:
            all_results.extend(lst)
            
        seen = set()
        unique = []
        for item in all_results:
            doi = item.get("doi")
            title = item.get("title", "").strip().lower()
            key = doi if doi else title
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
                
        return unique[:max_results]
