"""Three-factor confidence scoring for academic papers."""

import logging
import re
from typing import List, Dict
from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class PaperScorer:
    def __init__(self, model_provider: ModelProvider):
        self.llm = model_provider

    def score(self, paper: Dict) -> Dict:
        """Return three scores: methodology, results, novelty."""
        title = paper.get("title", "")
        abstract = paper.get("summary", "")
        authors = ", ".join(paper.get("authors", [])[:3])
        journal = paper.get("journal", "")

        prompt = f"""You are an academic research reviewer. Score the following paper on three dimensions from 0-100. Be strict and justify each score.

Paper: {title}
Authors: {authors}
Journal: {journal}
Abstract: {abstract}

Output format:
Methodology: [score] - [justification]
Results: [score] - [justification]
Novelty: [score] - [justification]
"""
        try:
            response = self.llm.generate(prompt, temperature=0.3)
            scores = self._parse(response)
            return scores
        except Exception as e:
            logger.error(f"Paper scoring failed: {e}")
            return {"methodology": 50, "results": 50, "novelty": 50, "justification": "Scoring failed due to exception."}

    def _parse(self, response: str) -> Dict:
        scores = {"methodology": 50, "results": 50, "novelty": 50, "justification": ""}
        for line in response.split("\n"):
            line = line.strip()
            if "Methodology" in line:
                parts = line.split("-")
                if len(parts) >= 1:
                    try:
                        match = re.search(r"\d+", parts[0])
                        if match:
                            scores["methodology"] = int(match.group())
                    except: pass
                    if len(parts) > 1:
                        scores["justification"] += f"Methodology: {parts[1].strip()}\n"
            elif "Results" in line:
                parts = line.split("-")
                if len(parts) >= 1:
                    try:
                        match = re.search(r"\d+", parts[0])
                        if match:
                            scores["results"] = int(match.group())
                    except: pass
                    if len(parts) > 1:
                        scores["justification"] += f"Results: {parts[1].strip()}\n"
            elif "Novelty" in line:
                parts = line.split("-")
                if len(parts) >= 1:
                    try:
                        match = re.search(r"\d+", parts[0])
                        if match:
                            scores["novelty"] = int(match.group())
                    except: pass
                    if len(parts) > 1:
                        scores["justification"] += f"Novelty: {parts[1].strip()}\n"
        return scores
