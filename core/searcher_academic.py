"""Academic search engine for ArXiv, PubMed, and OpenAlex."""

import httpx
import logging
import re
import time
import os
from typing import List, Dict, Optional
from xml.etree import ElementTree
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

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
        self.client = httpx.Client(timeout=30.0)

    def _wait_for_rate_limit(self, source: str):
        """Enforce rate limiting per source."""
        min_interval = self.rate_limits.get(source, 3.0)
        elapsed = time.time() - self.last_request_time.get(source, 0.0)
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_request_time[source] = time.time()

    def search_arxiv(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search ArXiv using the API."""
        self._wait_for_rate_limit("arxiv")
        arxiv_query = f"ti:{query} OR abs:{query}"
        params = {
            "search_query": arxiv_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        url = f"{self.arxiv_base}?{httpx.QueryParams(params)}"
        response = self.client.get(url)
        response.raise_for_status()
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
            title_node = entry.find("atom:title", ns)
            title = title_node.text.replace("\n", " ").strip() if title_node is not None and title_node.text else "Untitled"
            
            summary_node = entry.find("atom:summary", ns)
            summary = summary_node.text.replace("\n", " ").strip() if summary_node is not None and summary_node.text else ""
            
            authors = [a.text for a in entry.findall("atom:author/atom:name", ns) if a.text]
            
            pub_node = entry.find("atom:published", ns)
            published = pub_node.text[:10] if pub_node is not None and pub_node.text else ""
            year = published[:4] if published else "n.d."
            
            link = entry.find("atom:link[@rel='alternate']", ns)
            url = link.get("href") if link is not None else ""
            
            # Extract DOI if present
            doi = None
            doi_link = entry.find("atom:link[@title='doi']", ns)
            if doi_link is not None:
                doi = doi_link.get("href")
                
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
        return results

    def search_pubmed(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search PubMed using NCBI E-utilities."""
        self._wait_for_rate_limit("pubmed")
        # 1. Search for IDs
        esearch_url = f"{self.pubmed_base}esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "usehistory": "y",
            "email": self.user_email
        }
        search_resp = self.client.get(esearch_url, params=params)
        search_resp.raise_for_status()
        search_data = search_resp.json()
        ids = search_data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        # 2. Fetch abstracts
        self._wait_for_rate_limit("pubmed")
        efetch_url = f"{self.pubmed_base}efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
            "email": self.user_email
        }
        fetch_resp = self.client.get(efetch_url, params=params)
        fetch_resp.raise_for_status()
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
            pmid_elem = article.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""
            
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
        return results

    def search_openalex(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search OpenAlex."""
        self._wait_for_rate_limit("openalex")
        params = {
            "search": query,
            "per-page": max_results,
            "sort": "relevance_score"
        }
        url = f"{self.openalex_base}?{httpx.QueryParams(params)}"
        response = self.client.get(url, headers={"User-Agent": f"Scrutator/1.0 (mailto:{self.user_email})"})
        response.raise_for_status()
        data = response.json()
        results = []
        for work in data.get("results", []):
            authors = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
            # OpenAlex has abstract_inverted_index. Recreate abstract from it.
            abstract = ""
            inv_index = work.get("abstract_inverted_index")
            if inv_index:
                # Reconstruct abstract string from inverted index
                try:
                    words = []
                    for word, positions in inv_index.items():
                        for pos in positions:
                            words.append((pos, word))
                    words.sort()
                    abstract = " ".join([w[1] for w in words])
                except Exception as e:
                    logger.debug(f"Failed to reconstruct abstract: {e}")
            
            # DOI cleaning
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
