"""Detect contradictions and conflicting findings in literature."""

import logging
import re
from typing import List, Dict
from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class ContradictionDetector:
    def __init__(self, model_provider: ModelProvider):
        self.llm = model_provider
        self._contradictions = []

    def detect(self, papers: List[Dict]) -> List[Dict]:
        """Group findings and detect contradictions using abstract and full-text (if available)."""
        if len(papers) < 2:
            return []

        # Build detailed paper representations
        paper_summaries = []
        for i, p in enumerate(papers[:15]):  # limit to avoid token explosion
            # If full-text is available, include first 1000 characters of full text
            full_text_snip = ""
            if p.get("full_text"):
                full_text_snip = f"\nFull Text Snippet: {p['full_text'][:1000]}"
                
            authors_str = ", ".join(p.get("authors", [])[:2])
            paper_summaries.append(
                f"[{i+1}] Title: {p.get('title')}\n"
                f"Authors: {authors_str} ({p.get('year', 'N/A')})\n"
                f"Abstract: {p.get('summary', '')[:600]}\n"
                f"{full_text_snip}"
            )

        combined = "\n\n".join(paper_summaries)
        prompt = f"""You are an advanced academic research synthesizer. Analyze the following papers and identify contradictions, conflicting claims, or differing results.
        
Look specifically for:
- Claims that oppose each other (e.g. A says X increases Y, B says X decreases or has no effect on Y).
- Discrepancies in findings or conclusions.
- Disagreements on methodologies that lead to contrasting results.

Use explicit contradiction keywords (e.g., "contrary to", "disagrees", "refutes", "contradicts") where applicable in your analysis.

Papers:
{combined}

For each contradiction or major conflict identified, output exactly in the following format:
Finding A: [paper title/description + citation number, e.g. [1]]
Finding B: [paper title/description + citation number, e.g. [2]]
Conflict: [detailed description of the conflict or contradiction]
Confidence: [score 0-100]

If no contradictions exist, output: "No contradictions detected."
"""
        try:
            response = self.llm.generate(
                prompt,
                system_prompt="You are a meticulous, objective researcher who excels at mapping contrasting claims across academic papers."
            )
            contradictions = self._parse(response)
            
            # Merge LLM and citation network contradictions
            all_contradictions = []
            if hasattr(self, '_contradictions') and self._contradictions:
                all_contradictions.extend(self._contradictions)
            all_contradictions.extend(contradictions)
            
            # Deduplicate contradictions by finding keys
            seen = set()
            unique = []
            for c in all_contradictions:
                key = (c.get('finding_a', '').strip().lower(), c.get('finding_b', '').strip().lower())
                if key not in seen:
                    seen.add(key)
                    unique.append(c)
            return unique
        except Exception as e:
            logger.error(f"Contradiction detection failed: {e}")
            return getattr(self, '_contradictions', [])

    def integrate_citation_network(self, citation_network: 'CitationNetwork'):
        """Integrate contradictions from citation network with LLM detection."""
        if not hasattr(self, '_contradictions'):
            self._contradictions = []
        
        network_contradictions = citation_network.get_contradictions()
        for c in network_contradictions:
            title_a = c['paper_a']['title']
            title_b = c['paper_b']['title']
            authors_a = c['paper_a']['authors'][0] if c['paper_a']['authors'] else 'Unknown'
            authors_b = c['paper_b']['authors'][0] if c['paper_b']['authors'] else 'Unknown'
            
            self._contradictions.append({
                "finding_a": f"{title_a} ({authors_a})",
                "finding_b": f"{title_b} ({authors_b})",
                "conflict": f"Both papers cite '{c['common_reference']}' but may disagree in their interpretation.",
                "confidence": f"{int(c['confidence'] * 100)}%",
                "source": "citation_network"
            })
        logger.info(f"Integrated {len(network_contradictions)} citation network contradictions.")

    def _parse(self, response: str) -> List[Dict]:
        if "No contradictions detected" in response:
            return []
        contradictions = []
        blocks = response.split("\n\n")
        for block in blocks:
            if "Finding A" in block and "Finding B" in block:
                a = b = conflict = confidence = ""
                for line in block.split("\n"):
                    line_strip = line.strip()
                    line_clean = re.sub(r'^\*+\s*', '', line_strip)
                    line_clean = re.sub(r'\*+\s*$', '', line_clean)
                    
                    if line_clean.lower().startswith("finding a:"):
                        a = re.sub(r'(?i)^finding a:\s*', '', line_clean).strip()
                    elif line_clean.lower().startswith("finding b:"):
                        b = re.sub(r'(?i)^finding b:\s*', '', line_clean).strip()
                    elif line_clean.lower().startswith("conflict:"):
                        conflict = re.sub(r'(?i)^conflict:\s*', '', line_clean).strip()
                    elif line_clean.lower().startswith("confidence:"):
                        confidence = re.sub(r'(?i)^confidence:\s*', '', line_clean).strip()
                        
                if a and b:
                    contradictions.append({
                        "finding_a": a,
                        "finding_b": b,
                        "conflict": conflict,
                        "confidence": confidence
                    })
        return contradictions
