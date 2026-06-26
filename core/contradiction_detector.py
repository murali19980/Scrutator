"""Detect contradictions and conflicting findings in literature."""

import logging
from typing import List, Dict
from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class ContradictionDetector:
    def __init__(self, model_provider: ModelProvider):
        self.llm = model_provider

    def detect(self, papers: List[Dict]) -> List[Dict]:
        """Group findings and detect contradictions."""
        if len(papers) < 2:
            return []

        # Build a summary list
        paper_summaries = []
        for p in papers[:10]:  # limit to avoid token explosion
            paper_summaries.append(f"Title: {p.get('title')}\nAbstract: {p.get('summary', '')[:500]}\n")

        combined = "\n\n".join(paper_summaries)
        prompt = f"""You are a research synthesizer. Review the following papers and identify any contradictions or conflicting results.

Papers:
{combined}

For each contradiction, output:
- Finding A: [paper title/description]
- Finding B: [paper title/description]
- Conflict: [description]
- Confidence: [score 0-100]

If no contradictions exist, output: "No contradictions detected."
"""
        try:
            response = self.llm.generate(prompt, temperature=0.3)
            contradictions = self._parse(response)
            return contradictions
        except Exception as e:
            logger.error(f"Contradiction detection failed: {e}")
            return []

    def _parse(self, response: str) -> List[Dict]:
        if "No contradictions detected" in response:
            return []
        contradictions = []
        # Simple parsing: split by blank lines and look for patterns
        blocks = response.split("\n\n")
        for block in blocks:
            if "Finding A" in block and "Finding B" in block:
                # Extract fields
                a = b = conflict = confidence = ""
                for line in block.split("\n"):
                    line_strip = line.strip()
                    if "Finding A:" in line_strip:
                        a = line_strip.replace("Finding A:", "").strip()
                    elif "Finding B:" in line_strip:
                        b = line_strip.replace("Finding B:", "").strip()
                    elif "Conflict:" in line_strip:
                        conflict = line_strip.replace("Conflict:", "").strip()
                    elif "Confidence:" in line_strip:
                        confidence = line_strip.replace("Confidence:", "").strip()
                if a and b:
                    contradictions.append({
                        "finding_a": a,
                        "finding_b": b,
                        "conflict": conflict,
                        "confidence": confidence
                    })
        return contradictions
