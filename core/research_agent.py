"""Main orchestrator for Scrutator research loop."""

import logging
import os
import re
from typing import List, Dict, Optional, Set
from datetime import datetime
from tqdm import tqdm

from core.searcher import SearXNGClient
from core.scraper import ContentExtractor
from core.translator import Translator
from core.synthesizer import Synthesizer
from core.scorer import ConfidenceScorer
from core.stop_condition import should_stop
from core.reporter import Reporter
from core.model_provider import ModelProvider
from memory.manager import MemoryManager

logger = logging.getLogger(__name__)

class ResearchAgent:
    def __init__(self, config: Dict):
        self.config = config
        self.model_provider = ModelProvider(
            provider=config.get("model", {}).get("provider", "openrouter"),
            model=config.get("model", {}).get("model", "openrouter/free"),
            temperature=config.get("model", {}).get("temperature", 0.7),
            max_tokens=config.get("model", {}).get("max_tokens", 4096)
        )
        self.searcher = SearXNGClient(
            base_url=config.get("search", {}).get("searxng_url", "http://localhost:8888"),
            fallback_to_public=config.get("search", {}).get("fallback_to_public", True)
        )
        self.scraper = ContentExtractor()
        self.translator = Translator(self.model_provider)
        self.synthesizer = Synthesizer(self.model_provider)
        self.scorer = ConfidenceScorer(self.model_provider)
        self.reporter = Reporter()
        self.memory = None
        if config.get("memory", {}).get("enabled", False):
            self.memory = MemoryManager(config.get("memory", {}))

        self.all_sources = []
        self.loop_history = []
        self.final_report = None

    def run(
        self,
        query: str,
        languages: List[str] = None,
        mode: str = "balanced",
        max_loops: Optional[int] = None,
        regions: List[str] = None,
        memory_mode: str = "ask",  # auto, ask, off
        feedback_callback = None
    ) -> Dict:
        """
        Main research entry point. Executes the iterative research loop.
        """
        logger.info(f"Starting research for query: {query}")
        languages = languages or ["en"]
        
        # Expand regions to languages using country map
        if regions:
            from config.country_language_map import country_language_map
            # Map country codes in country_language_map (which is nested)
            # Just in case, let's load it directly:
            # { "country_language_map": { "US": ["en"] } }
            # Wait, let's make it robust:
            cmap = self.config.get("country_language_map", {})
            if not cmap:
                cmap = {
                    "US": ["en"], "CN": ["zh"], "DE": ["de"], "RU": ["ru"],
                    "FR": ["fr"], "JP": ["ja"], "KR": ["ko"]
                }
            for region in regions:
                reg_upper = region.upper()
                if reg_upper in cmap:
                    languages.extend(cmap[reg_upper])
            languages = list(set(languages))

        loop_limit = max_loops or self.config.get("research", {}).get("loop_limits", {}).get(mode, 7)
        confidence_threshold = self.config.get("research", {}).get("confidence_threshold", 85)
        min_sources = self.config.get("research", {}).get("min_sources", 10)
        stop_early = self.config.get("research", {}).get("stop_early", True)

        current_loop = 0
        overall_confidence = 0.0
        refined_query = query
        previous_urls = set()
        
        # Apply memories (preferences/feedback) if memory is enabled and we are not in 'off' mode
        applied_memories = []
        if self.memory and memory_mode != "off":
            # Search memory for topic
            memories = self.memory.find(query)
            if memories:
                if memory_mode == "auto":
                    applied_memories = memories
                    logger.info(f"Automatically applied {len(applied_memories)} memories.")
                elif memory_mode == "ask" and feedback_callback:
                    # Interact through callback
                    applied_memories = feedback_callback(memories)
                else:
                    # Fallback default: log and apply preferences automatically
                    applied_memories = [m for m in memories if m.type == "preference"]
                    logger.info(f"Applied {len(applied_memories)} preference memories.")

        # Inject memory preferences into the refined query or system/user prompts if applicable
        pref_instruction = ""
        if applied_memories:
            prefs = [m.content for m in applied_memories]
            pref_instruction = "\nUser preferences applied from memory:\n" + "\n".join(f"- {p}" for p in prefs)
            logger.info(f"Preferences injected into research: {prefs}")

        # Reset state for run
        self.all_sources = []
        self.loop_history = []

        logger.info(f"Loop limit: {loop_limit}, Confidence threshold: {confidence_threshold}")

        while current_loop < loop_limit:
            current_loop += 1
            logger.info(f"--- LOOP {current_loop} START ---")

            # 1. Search for each language
            new_sources = []
            for lang in languages:
                logger.info(f"Searching for '{refined_query}' in language '{lang}'...")
                results = self.searcher.search(refined_query, language=lang, count=5)
                logger.info(f"Found {len(results)} results for language '{lang}'")
                new_sources.extend(results)

            # 2. Scrape and Translate
            extracted = []
            logger.info(f"Scraping {len(new_sources)} urls found in search...")
            for result in new_sources:
                url = result["url"]
                if url in previous_urls:
                    continue  # Skip duplicate URLs
                
                content = self.scraper.extract(url)
                if content and content.get("text"):
                    # Translate if not English
                    if result["language"] != "en" and self.config.get("translation", {}).get("enabled", True):
                        logger.info(f"Translating source: {content.get('title')} from {result['language']}")
                        content["text"] = self.translator.translate(content["text"], source_lang=result["language"])
                    content["language"] = result["language"]
                    extracted.append(content)
                    previous_urls.add(url)

            # 3. Deduplicate and Add
            if not extracted:
                logger.info("No new content extracted in this loop.")
            else:
                self.all_sources.extend(extracted)
                logger.info(f"Successfully extracted {len(extracted)} new sources. Total unique sources: {len(self.all_sources)}")

            # 4. Synthesize current findings
            logger.info("Synthesizing current gathered findings...")
            synthesis = self.synthesizer.synthesize(self.all_sources, query)

            # 5. Score confidence
            logger.info("Scoring confidence of synthesized findings...")
            score_result = self.scorer.score_finding(synthesis["summary"], self.all_sources)
            overall_confidence = score_result["score"]
            logger.info(f"Confidence score for this loop: {overall_confidence}/100. Justification: {score_result['justification']}")

            self.loop_history.append({
                "loop": current_loop,
                "query": refined_query,
                "sources_found": len(extracted),
                "confidence": overall_confidence,
                "summary": synthesis["summary"],
                "key_insights": synthesis["key_insights"]
            })

            # 6. Check Stop Condition
            current_urls = {s["url"] for s in extracted}
            if should_stop(
                confidence=overall_confidence,
                source_count=len(self.all_sources),
                loop_count=current_loop,
                max_loops=loop_limit,
                previous_urls=previous_urls - current_urls,
                current_urls=current_urls,
                confidence_threshold=confidence_threshold,
                min_sources=min_sources,
                stop_early=stop_early
            ):
                logger.info("Stop condition met. Ending research loop.")
                break

            # 7. Refine Query for next loop
            refined_query = self._refine_query(query, synthesis["summary"], pref_instruction)
            logger.info(f"Refined query for loop {current_loop + 1}: '{refined_query}'")

        # Compile final report data
        report_data = {
            "query": query,
            "overall_confidence": overall_confidence,
            "sources": self.all_sources,
            "loop_history": self.loop_history,
            "findings": self.loop_history[-1] if self.loop_history else {
                "summary": "No research completed.", "key_insights": []
            },
            "detailed_synthesis": synthesis.get("detailed_synthesis", "Detailed synthesis not available."),
            "followup_questions": self._generate_followup_questions(query, synthesis.get("summary", ""))
        }

        # Generate report text
        report_markdown = self.reporter.generate_markdown(
            query=report_data["query"],
            findings=report_data["findings"],
            confidence_overall=report_data["overall_confidence"],
            sources=report_data["sources"],
            loop_history=report_data["loop_history"],
            health_check={"status": "Healthy", "loops_run": current_loop},
            followup_questions=report_data["followup_questions"]
        )
        report_data["markdown"] = report_markdown

        # Write report to output directory
        reports_dir = self.config.get("output", {}).get("reports_dir", "./reports")
        os.makedirs(reports_dir, exist_ok=True)
        # Create a safe filename
        safe_query = re.sub(r'[^a-zA-Z0-9_\-]', '_', query)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(reports_dir, f"report_{safe_query}_{timestamp}.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_markdown)
        
        report_data["report_path"] = report_path
        logger.info(f"Saved final report to {report_path}")

        # Update memory with query and key findings
        if self.memory and memory_mode != "off" and self.loop_history:
            from memory.types import KnowledgeMemory
            findings_summary = "\n".join(f"- {insight}" for insight in report_data["findings"].get("key_insights", []))
            mem_content = f"Researched '{query}' on {datetime.now().strftime('%Y-%m-%d')}. Key findings:\n{findings_summary}"
            self.memory.add(KnowledgeMemory(
                id=f"research_{timestamp}",
                topic=query,
                content=mem_content,
                timestamp=datetime.now(),
                confidence=overall_confidence,
                metadata={"report_path": report_path}
            ))
            logger.info("Saved search findings to Knowledge Memory.")

        return report_data

    def _refine_query(self, original_query: str, summary: str, preferences: str) -> str:
        """Use LLM to refine the search query based on current gaps."""
        prompt = f"""You are a research query planner. Based on the original query and the summary of findings we have gathered so far, propose a new, specific search query to find missing details, resolve contradictions, or seek deeper info. Do not repeat what is already known.
        
Original Query: {original_query}
Current Findings Summary: {summary}
{preferences}

Output ONLY the refined search query (one sentence/phrase) and nothing else:"""
        try:
            refined = self.model_provider.generate(prompt, temperature=0.5)
            # Remove any quotes or preamble
            refined = refined.strip().strip('"\'')
            return refined or original_query
        except Exception as e:
            logger.warning(f"Query refinement failed, using fallback append: {e}")
            return f"{original_query} latest developments details"

    def _generate_followup_questions(self, query: str, summary: str) -> List[str]:
        """Generate follow up research questions."""
        prompt = f"""Given the following summary of research on '{query}', suggest 3 logical follow-up research questions to explore.
        
Summary: {summary}

Output format:
1. Question 1
2. Question 2
3. Question 3"""
        try:
            response = self.model_provider.generate(prompt, temperature=0.5)
            questions = []
            for line in response.split("\n"):
                line = line.strip()
                match = re.match(r"^\d+[\.\)]\s*(.*)", line)
                if match:
                    questions.append(match.group(1).strip())
            return questions[:3] or ["What are the next developments?", "Who are the key players?", "What are the limitations?"]
        except Exception as e:
            logger.warning(f"Failed to generate follow-up questions: {e}")
            return ["What are the next developments?", "Who are the key players?", "What are the limitations?"]
