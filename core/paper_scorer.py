"""Three-factor confidence scoring for academic papers."""

import logging
import re
import math
from typing import List, Dict, Optional
from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class PaperScorer:
    def __init__(self, model_provider: ModelProvider, ensemble_runs: int = 1):
        self.llm = model_provider
        self.ensemble_runs = ensemble_runs

    def score(self, paper: Dict) -> Dict:
        """Return three scores: methodology, results, novelty.
        
        Runs ensemble scoring if ensemble_runs > 1, computing mean and standard deviation.
        """
        title = paper.get("title", "")
        abstract = paper.get("summary", "")
        authors = ", ".join(paper.get("authors", [])[:3])
        journal = paper.get("journal", "")
        full_text = paper.get("full_text", "")

        text_context = abstract
        if full_text:
            text_context += "\n[Full Text Excerpt (Introduction, Methods, early Results)]:\n" + full_text[:8000]

        prompt = f"""You are an academic research reviewer. Score the following paper on three dimensions from 0-100. Be strict and justify each score.

Paper: {title}
Authors: {authors}
Journal: {journal}
Content (Abstract or Full-Text Excerpt): {text_context}

Output format:
Methodology: [score] - [justification]
Results: [score] - [justification]
Novelty: [score] - [justification]
"""
        if self.ensemble_runs <= 1:
            try:
                response = self.llm.generate(prompt, system_prompt="You are a strict, objective academic reviewer.")
                scores = self._parse(response)
                scores["methodology_sd"] = 0.0
                scores["results_sd"] = 0.0
                scores["novelty_sd"] = 0.0
                return scores
            except Exception as e:
                logger.error(f"Paper scoring failed: {e}")
                return {
                    "methodology": 50, "results": 50, "novelty": 50,
                    "methodology_sd": 0.0, "results_sd": 0.0, "novelty_sd": 0.0,
                    "justification": "Scoring failed due to exception."
                }

        # Ensemble runs
        methodology_scores = []
        results_scores = []
        novelty_scores = []
        justifications = []

        original_temp = self.llm.temperature
        self.llm.temperature = max(0.5, original_temp)

        for r in range(self.ensemble_runs):
            try:
                response = self.llm.generate(prompt, system_prompt="You are a strict, objective academic reviewer.")
                parsed = self._parse(response)
                methodology_scores.append(parsed["methodology"])
                results_scores.append(parsed["results"])
                novelty_scores.append(parsed["novelty"])
                if parsed["justification"]:
                    justifications.append(f"Run {r+1}: {parsed['justification'].strip()}")
            except Exception as e:
                logger.warning(f"Ensemble scoring run {r+1} failed: {e}")

        self.llm.temperature = original_temp

        if not methodology_scores:
            return {
                "methodology": 50, "results": 50, "novelty": 50,
                "methodology_sd": 0.0, "results_sd": 0.0, "novelty_sd": 0.0,
                "justification": "All ensemble runs failed."
            }

        def compute_mean_sd(lst: List[int]):
            mean = sum(lst) / len(lst)
            variance = sum((x - mean) ** 2 for x in lst) / len(lst)
            sd = math.sqrt(variance)
            return round(mean), round(sd, 1)

        m_mean, m_sd = compute_mean_sd(methodology_scores)
        r_mean, r_sd = compute_mean_sd(results_scores)
        n_mean, n_sd = compute_mean_sd(novelty_scores)

        combined_justification = "\n\n".join(justifications)
        return {
            "methodology": m_mean,
            "methodology_sd": m_sd,
            "results": r_mean,
            "results_sd": r_sd,
            "novelty": n_mean,
            "novelty_sd": n_sd,
            "justification": combined_justification
        }

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
                    except (ValueError, TypeError):
                        pass
                    if len(parts) > 1:
                        scores["justification"] += f"Methodology: {parts[1].strip()}\n"
            elif "Results" in line:
                parts = line.split("-")
                if len(parts) >= 1:
                    try:
                        match = re.search(r"\d+", parts[0])
                        if match:
                            scores["results"] = int(match.group())
                    except (ValueError, TypeError):
                        pass
                    if len(parts) > 1:
                        scores["justification"] += f"Results: {parts[1].strip()}\n"
            elif "Novelty" in line:
                parts = line.split("-")
                if len(parts) >= 1:
                    try:
                        match = re.search(r"\d+", parts[0])
                        if match:
                            scores["novelty"] = int(match.group())
                    except (ValueError, TypeError):
                        pass
                    if len(parts) > 1:
                        scores["justification"] += f"Novelty: {parts[1].strip()}\n"
        return scores
