"""Export search results to BibTeX format."""

from typing import List, Dict
import re

def to_bibtex(paper: Dict) -> str:
    """Convert a paper dict to a BibTeX entry."""
    authors = paper.get("authors", [])
    if not authors:
        authors = ["Anonymous"]
    author_str = " and ".join(authors)
    title = paper.get("title", "").strip()
    year = paper.get("year", "n.d.")
    journal = paper.get("journal", "")
    doi = paper.get("doi", "")
    
    # Generate a key: first author last name + year + first word of title
    first_author = authors[0]
    last_name = first_author.split()[-1] if first_author.split() else "unknown"
    # remove non-alphanumeric chars
    last_name = re.sub(r'\W+', '', last_name)
    
    title_words = re.sub(r'[^\w\s]', '', title).split()
    first_title_word = title_words[0].lower() if title_words else ""
    first_title_word = re.sub(r'\W+', '', first_title_word)
    
    key = f"{last_name.lower()}{year}{first_title_word}"
    if not key or key == "n.d.":
        key = f"paper_{hash(title) % 10000}"

    entry_type = 'article' if journal else 'misc'
    entry = f"""@{entry_type}{{{key},
  author = {{{author_str}}},
  title = {{{title}}},
  year = {{{year}}},
  journal = {{{journal}}},
  doi = {{{doi}}}
}}"""
    return entry

def export_bibtex(papers: List[Dict], filename: str = "references.bib"):
    """Export all papers to a .bib file."""
    with open(filename, "w", encoding="utf-8") as f:
        for paper in papers:
            f.write(to_bibtex(paper) + "\n\n")
