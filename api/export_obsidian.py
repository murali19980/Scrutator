"""Obsidian folder note package exporter."""

import os
import re
from typing import List, Dict

def sanitize_filename(name: str) -> str:
    """Make filename safe for filesystem and Obsidian links."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name[:60].strip()

def export_obsidian(papers: List[Dict], scores: List[Dict], report_data: Dict, output_dir: str):
    """Compile the review into a directory of Obsidian markdown notes."""
    from datetime import datetime
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Create main overview index note
    index_content = f"""---
tags: [literature-review, index]
query: "{report_data.get('query')}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
confidence_score: {report_data.get('confidence', 0.0)}
---
# Literature Review: {report_data.get('query')}

## Executive Summary
{report_data.get('summary', '')}

## Key Themes
"""
    for t in report_data.get("themes", []):
        index_content += f"- {t}\n"
        
    index_content += "\n## Reviewed Papers Matrix\n"
    index_content += "| Paper | Year | Methodology | Results | Novelty | Source |\n"
    index_content += "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    
    # Write notes for each paper and append to matrix
    for i, paper in enumerate(papers):
        s = scores[i] if i < len(scores) else {}
        title = paper.get("title", "Untitled")
        safe_title = sanitize_filename(title)
        year = paper.get("year", "n.d.")
        source = paper.get("source", "unknown")
        
        index_content += f"| [[{safe_title}]] | {year} | {s.get('methodology', '')} | {s.get('results', '')} | {s.get('novelty', '')} | {source} |\n"
        
        # Paper individual note
        authors_yaml = str(paper.get("authors", []))
        paper_content = f"""---
tags: [literature-review, paper]
title: "{title.replace('"', '\\"')}"
authors: {authors_yaml}
year: {year}
doi: "{paper.get('doi') or ''}"
url: "{paper.get('url') or ''}"
source: {source}
methodology_score: {s.get('methodology', 50)}
results_score: {s.get('results', 50)}
novelty_score: {s.get('novelty', 50)}
---
# {title}

- **Authors:** {", ".join(paper.get("authors", []))}
- **Journal/Source:** {paper.get("journal", "N/A")} ({year})
- **DOI:** [{paper.get("doi", "N/A")}](https://doi.org/{paper.get("doi", "")})
- **Original Link:** [{source.upper()}]({paper.get("url", "")})

## Abstract
{paper.get("summary", "")}

## Scrutator Evaluation
- **Methodology Score:** {s.get('methodology', 50)}/100
- **Results Consistency:** {s.get('results', 50)}/100
- **Novelty & Significance:** {s.get('novelty', 50)}/100

### Review Justification
{s.get('justification', 'No evaluation details provided.')}
"""
        with open(os.path.join(output_dir, f"{safe_title}.md"), "w", encoding="utf-8") as f:
            f.write(paper_content)
            
    # Add gaps and contradictions to index note
    contradictions = report_data.get("contradictions", [])
    if contradictions:
        index_content += "\n## Contradictions & Conflicting Findings\n"
        for c in contradictions:
            index_content += f"- **Finding A:** {c.get('finding_a')}\n"
            index_content += f"  **Finding B:** {c.get('finding_b')}\n"
            index_content += f"  **Conflict:** {c.get('conflict')}\n"
            
    gaps = report_data.get("gaps", [])
    if gaps:
        index_content += "\n## Research Gaps\n"
        for g in gaps:
            index_content += f"- {g}\n"
            
    with open(os.path.join(output_dir, "Overview_Index.md"), "w", encoding="utf-8") as f:
        f.write(index_content)
