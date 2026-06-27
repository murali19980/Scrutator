"""CSV reference list exporter."""

import csv
from typing import List, Dict

def export_csv(papers: List[Dict], scores: List[Dict], filename: str = "references.csv"):
    """Export papers and their scores to a CSV file."""
    headers = [
        "Title", "Authors", "Journal/Venue", "Year", "DOI", "URL", "Source",
        "Methodology Score", "Results Score", "Novelty Score"
    ]
    
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        for i, paper in enumerate(papers):
            s = scores[i] if i < len(scores) else {}
            authors_str = "; ".join(paper.get("authors", []))
            
            row = [
                paper.get("title", "Untitled"),
                authors_str,
                paper.get("journal", ""),
                paper.get("year", "n.d."),
                paper.get("doi", ""),
                paper.get("url", ""),
                paper.get("source", ""),
                s.get("methodology", ""),
                s.get("results", ""),
                s.get("novelty", "")
            ]
            writer.writerow(row)
