"""Confidence scoring module."""

import logging
import re
from typing import List, Dict
from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class ConfidenceScorer:
    def __init__(self, model_provider: ModelProvider):
        self.model_provider = model_provider

    def score_finding(self, finding: str, sources: List[Dict]) -> Dict:
        """Score the confidence of a finding based on supporting sources."""
        if not sources:
            return {"score": 0.0, "justification": "No sources available."}

        source_summaries = "\n".join([
            f"- {s.get('title', 'Untitled')} ({s.get('url', '')})"
            for s in sources[:5]
        ])

        prompt = f"""Rate your confidence (0-100) for the following research finding. Be strict:
- 100 = official source/citation
- 80 = multiple consistent sources
- 50 = single source
- 20 = speculation or unclear
- 0 = completely unsupported

Finding: {finding}

Sources:
{source_summaries}

Justify your score briefly, mentioning the number of sources and their authority.

Output format:
Score: [number]
Justification: [text]"""

        try:
            response = self.model_provider.generate(prompt, temperature=0.3)
            score = 50
            justification = "Unable to parse score."
            
            score_match = re.search(r"Score:\s*(\d+)", response, re.IGNORECASE)
            justification_match = re.search(r"Justification:\s*(.*)", response, re.DOTALL | re.IGNORECASE)
            
            if score_match:
                try:
                    score = int(score_match.group(1).strip())
                except ValueError:
                    pass
            
            if justification_match:
                justification = justification_match.group(1).strip()
            else:
                # Fallback line parsing
                for line in response.split("\n"):
                    line = line.strip()
                    if line.lower().startswith("score:"):
                        try:
                            score = int(line[len("score:"):].strip())
                        except:
                            pass
                    elif line.lower().startswith("justification:"):
                        justification = line[len("justification:"):].strip()
                        
            return {
                "score": min(max(score, 0), 100),
                "justification": justification
            }
        except Exception as e:
            logger.error(f"Confidence scoring failed: {e}")
            return {"score": 50, "justification": "Scoring failed due to error."}
