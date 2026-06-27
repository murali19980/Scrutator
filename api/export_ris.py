"""RIS citation format exporter for academic references."""

from typing import List, Dict
import re

def to_ris(paper: Dict) -> str:
    """Convert a paper dictionary to a RIS entry."""
    # Determine type
    source = paper.get("source", "arxiv")
    if source == "pubmed" or paper.get("journal"):
        ty = "JOUR"  # Journal Article
    else:
        ty = "GEN"   # General generic

    lines = []
    lines.append(f"TY  - {ty}")
    lines.append(f"TI  - {paper.get('title', 'Untitled').strip()}")
    
    # Authors: Last, First format or just name
    for author in paper.get("authors", []):
        # Simple convert to Last, First if "First Last" format
        parts = author.strip().split()
        if len(parts) >= 2:
            last = parts[-1]
            firsts = " ".join(parts[:-1])
            lines.append(f"AU  - {last}, {firsts}")
        else:
            lines.append(f"AU  - {author.strip()}")
            
    if not paper.get("authors"):
        lines.append("AU  - Anonymous")
        
    year = paper.get("year", "n.d.")
    if year and year != "n.d.":
        lines.append(f"PY  - {year}///")
        
    journal = paper.get("journal")
    if journal:
        lines.append(f"JO  - {journal.strip()}")
        
    doi = paper.get("doi")
    if doi:
        lines.append(f"DO  - {doi.strip()}")
        
    url = paper.get("url")
    if url:
        lines.append(f"UR  - {url.strip()}")
        
    abstract = paper.get("summary")
    if abstract:
        # Strip newlines or replace with spaces for RIS compliance
        clean_abs = abstract.replace("\n", " ").strip()
        lines.append(f"N2  - {clean_abs}")
        
    lines.append("ER  - ")
    return "\n".join(lines)

def export_ris(papers: List[Dict], filename: str = "references.ris"):
    """Export list of papers to a .ris file."""
    with open(filename, "w", encoding="utf-8") as f:
        for paper in papers:
            f.write(to_ris(paper) + "\n\n")
