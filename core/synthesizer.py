"""Synthesis and summarization module."""

import logging
from typing import List, Dict
import re
from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class Synthesizer:
    def __init__(self, model_provider: ModelProvider):
        self.model_provider = model_provider

    def synthesize(self, sources: List[Dict], query: str) -> Dict:
        """Synthesize findings from a list of sources."""
        if not sources:
            return {
                "summary": "No sources available.",
                "key_insights": [],
                "detailed_synthesis": "No content to synthesize."
            }

        # Build source text (truncate to avoid token overflow)
        source_texts = []
        for i, src in enumerate(sources[:10], 1):
            text = src.get("text", "")[:1500]  # Limit per source
            title = src.get("title", "Untitled")
            url = src.get("url", "")
            source_texts.append(f"Source {i}: {title} ({url})\n{text}\n")

        combined = "\n\n".join(source_texts)

        prompt = f"""You are a research synthesizer. Given the following sources and the research query, produce:
1. A 2-3 paragraph executive summary that answers the query.
2. A list of 3-5 key insights (each as a short bullet point).
3. A more detailed synthesis (1-2 paragraphs) that integrates the findings.

Research query: {query}

Sources:
{combined}

Output format:
Summary:
[Your executive summary paragraphs here]

Key Insights:
- [Insight 1]
- [Insight 2]
- [Insight 3]

Detailed Synthesis:
[Your detailed synthesis paragraphs here]"""

        try:
            response = self.model_provider.generate(prompt, temperature=0.5)
            
            # Robust parsing using regex & sections
            summary_match = re.search(r"Summary:\s*(.*?)(?=Key Insights:|$)", response, re.DOTALL | re.IGNORECASE)
            insights_match = re.search(r"Key Insights:\s*(.*?)(?=Detailed Synthesis:|$)", response, re.DOTALL | re.IGNORECASE)
            detailed_match = re.search(r"Detailed Synthesis:\s*(.*)", response, re.DOTALL | re.IGNORECASE)
            
            summary = summary_match.group(1).strip() if summary_match else ""
            insights_block = insights_match.group(1).strip() if insights_match else ""
            detailed = detailed_match.group(1).strip() if detailed_match else ""
            
            # Extract bullet points
            key_insights = []
            if insights_block:
                for line in insights_block.split("\n"):
                    line = line.strip()
                    if line.startswith("-") or line.startswith("*"):
                        key_insights.append(line.lstrip("-* ").strip())
                    elif line and key_insights:
                        # Append to last insight if it is a continuation line
                        key_insights[-1] += " " + line
            
            # Fallback parsing if regex failed
            if not summary or not key_insights or not detailed:
                logger.warning("Regex parsing of LLM response had empty fields; falling back to line parsing.")
                summary_lines = []
                insight_lines = []
                detailed_lines = []
                current_section = None
                
                for line in response.split("\n"):
                    line_strip = line.strip()
                    if line_strip.lower().startswith("summary:"):
                        current_section = "summary"
                        val = line_strip[len("summary:"):].strip()
                        if val:
                            summary_lines.append(val)
                    elif line_strip.lower().startswith("key insights:"):
                        current_section = "insights"
                    elif line_strip.lower().startswith("detailed synthesis:"):
                        current_section = "detailed"
                        val = line_strip[len("detailed synthesis:"):].strip()
                        if val:
                            detailed_lines.append(val)
                    elif line_strip:
                        if current_section == "summary":
                            summary_lines.append(line_strip)
                        elif current_section == "insights":
                            if line_strip.startswith("-") or line_strip.startswith("*"):
                                insight_lines.append(line_strip.lstrip("-* ").strip())
                        elif current_section == "detailed":
                            detailed_lines.append(line_strip)
                
                if not summary and summary_lines:
                    summary = " ".join(summary_lines)
                if not key_insights and insight_lines:
                    key_insights = insight_lines
                if not detailed and detailed_lines:
                    detailed = " ".join(detailed_lines)

            return {
                "summary": summary or "Summary not available.",
                "key_insights": key_insights or ["No key insights extracted."],
                "detailed_synthesis": detailed or "Detailed synthesis not available."
            }
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            e_str = str(e).lower()
            if "unauthorized" in e_str or "api key" in e_str or "credentials" in e_str or "401" in e_str or "403" in e_str:
                raise
            return {
                "summary": "Synthesis failed due to an error.",
                "key_insights": [],
                "detailed_synthesis": "An error occurred during synthesis."
            }
