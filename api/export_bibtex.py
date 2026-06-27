"""Export search results to BibTeX format."""

from typing import List, Dict
import re

def fetch_crossref_metadata(doi: str) -> dict:
    """Fetch publication details from Crossref using DOI."""
    if not doi:
        return {}
    clean_doi = doi.strip()
    if clean_doi.startswith("http://dx.doi.org/"):
        clean_doi = clean_doi.replace("http://dx.doi.org/", "")
    elif clean_doi.startswith("https://doi.org/"):
        clean_doi = clean_doi.replace("https://doi.org/", "")
        
    url = f"https://api.crossref.org/works/{clean_doi}"
    try:
        from core.scraper import get_safe_session
        session = get_safe_session()
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            item = resp.json().get("message", {})
            metadata = {}
            if "volume" in item:
                metadata["volume"] = item["volume"]
            if "issue" in item:
                metadata["number"] = item["issue"]
            if "page" in item:
                metadata["pages"] = item["page"]
            if "publisher" in item:
                metadata["publisher"] = item["publisher"]
            if "container-title" in item and item["container-title"]:
                metadata["journal"] = item["container-title"][0]
            return metadata
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to query Crossref for DOI {clean_doi}: {e}")
    return {}

def to_bibtex(paper: Dict) -> str:
    """Convert a paper dict to a BibTeX entry, resolving missing metadata via Crossref if possible."""
    doi = paper.get("doi", "")
    crossref_data = {}
    if doi:
        crossref_data = fetch_crossref_metadata(doi)
        
    authors = paper.get("authors", [])
    if not authors:
        authors = ["Anonymous"]
    author_str = " and ".join(authors)
    title = paper.get("title", "").strip()
    year = paper.get("year", "n.d.")
    
    # Merge paper metadata and crossref data
    journal = paper.get("journal") or crossref_data.get("journal") or ""
    volume = crossref_data.get("volume") or ""
    number = crossref_data.get("number") or ""
    pages = crossref_data.get("pages") or ""
    publisher = crossref_data.get("publisher") or ""
    url = paper.get("url") or ""
    
    # Generate key
    first_author = authors[0]
    last_name = first_author.split()[-1] if first_author.split() else "unknown"
    last_name = re.sub(r'\W+', '', last_name)
    
    title_words = re.sub(r'[^\w\s]', '', title).split()
    first_title_word = title_words[0].lower() if title_words else ""
    first_title_word = re.sub(r'\W+', '', first_title_word)
    
    key = f"{last_name.lower()}{year}{first_title_word}"
    if not key or key == "n.d.":
        key = f"paper_{hash(title) % 10000}"
        
    # Build BibTeX fields
    fields = [
        f"  author = {{{author_str}}}",
        f"  title = {{{title}}}",
        f"  year = {{{year}}}"
    ]
    if journal:
        fields.append(f"  journal = {{{journal}}}")
    if volume:
        fields.append(f"  volume = {{{volume}}}")
    if number:
        fields.append(f"  number = {{{number}}}")
    if pages:
        fields.append(f"  pages = {{{pages}}}")
    if publisher:
        fields.append(f"  publisher = {{{publisher}}}")
    if doi:
        fields.append(f"  doi = {{{doi}}}")
    if url:
        fields.append(f"  url = {{{url}}}")
        
    entry_type = 'article' if journal else 'misc'
    entry_fields = ",\n".join(fields)
    entry = f"@{entry_type}{{{key},\n{entry_fields}\n}}"
    return entry

def export_bibtex(papers: List[Dict], filename: str = "references.bib"):
    """Export all papers to a .bib file."""
    with open(filename, "w", encoding="utf-8") as f:
        for paper in papers:
            f.write(to_bibtex(paper) + "\n\n")
