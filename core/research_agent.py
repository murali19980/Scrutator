"""Main orchestrator for Scrutator research loop."""

import logging
import os
import re
import asyncio
import anyio
from typing import List, Dict, Optional, Set
from datetime import datetime
from tqdm import tqdm
from core.feedback import ProgressTracker, ProgressUpdate

from core.searcher import SearXNGClient
from core.scraper import ContentExtractor
from core.translator import Translator
from core.synthesizer import Synthesizer
from core.scorer import ConfidenceScorer
from core.stop_condition import should_stop
from core.reporter import Reporter
from core.model_provider import ModelProvider
from memory.manager import MemoryManager

# Scrutator Academic imports
from core.searcher_academic import AcademicSearcher
from core.paper_scorer import PaperScorer
from core.contradiction_detector import ContradictionDetector
from core.reporter_academic import AcademicReporter
from api.export_bibtex import export_bibtex
from core.citation_network import CitationNetwork

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

        self.academic_searcher = AcademicSearcher()
        
        # Check if a separate scorer model is configured to mitigate self-evaluation bias
        scorer_provider = config.get("academic", {}).get("scorer_provider")
        scorer_model = config.get("academic", {}).get("scorer_model")
        if scorer_provider and scorer_model:
            scorer_llm = ModelProvider(
                provider=scorer_provider,
                model=scorer_model,
                temperature=config.get("model", {}).get("temperature", 0.7),
                max_tokens=config.get("model", {}).get("max_tokens", 4096)
            )
            logger.info(f"Initialized separate LLM provider for paper scoring: {scorer_provider}/{scorer_model}")
        else:
            scorer_llm = self.model_provider

        ensemble_runs = config.get("academic", {}).get("ensemble_runs", 1)
        self.paper_scorer = PaperScorer(scorer_llm, ensemble_runs=ensemble_runs)
        self.contradiction_detector = ContradictionDetector(self.model_provider)
        self.academic_reporter = AcademicReporter()

        self.all_sources = []
        self.loop_history = []
        self.final_report = None
        self._cancelled = False
        self._cancel_scope = None
        self.progress_tracker = None

    def run(
        self,
        query: str,
        languages: List[str] = None,
        mode: str = "balanced",
        max_loops: Optional[int] = None,
        regions: List[str] = None,
        memory_mode: str = "ask",  # auto, ask, off
        feedback_callback = None,
        academic: bool = False,
        uploaded_papers: List[Dict] = None
    ) -> Dict:
        """
        Main research entry point. Executes the iterative research loop.
        """
        if academic:
            return self._run_academic(query, mode, max_loops, feedback_callback, uploaded_papers)
            
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

    def _run_academic(self, query: str, mode: str, max_loops: Optional[int] = None, feedback_callback = None, uploaded_papers: List[Dict] = None) -> Dict:
        """Run an academic literature review."""
        logger.info(f"Starting academic literature review for: {query}")
        
        if feedback_callback:
            feedback_callback("Searching academic databases (ArXiv, PubMed, OpenAlex)...")
            
        loop_limit = max_loops or self.config.get("research", {}).get("loop_limits", {}).get(mode, 5)
        # Search all configured databases
        papers = self.academic_searcher.search_all(query, max_results=loop_limit * 5)
        if uploaded_papers:
            papers = uploaded_papers + papers
        if not papers:
            logger.warning("No academic papers found.")
            return {"error": "No academic papers found."}

        # Unpaywall PDF full text extraction (if enabled)
        fetch_full_text = self.config.get("academic", {}).get("fetch_full_text", True)
        if fetch_full_text:
            if feedback_callback:
                feedback_callback(f"Found {len(papers)} unique papers. Checking for Open-Access PDFs...")
            from core.scraper import download_and_extract_pdf, get_safe_session, is_safe_url
            session = get_safe_session()
            for p in papers:
                doi = p.get("doi")
                if doi:
                    try:
                        email = self.user_email
                        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
                        if is_safe_url(unpaywall_url):
                            resp = session.get(unpaywall_url, timeout=10)
                            if resp.status_code == 200:
                                data = resp.json()
                                if data.get("is_oa") and data.get("best_oa_location"):
                                    pdf_url = data["best_oa_location"].get("url_for_pdf")
                                    if pdf_url:
                                        logger.info(f"Downloading Open-Access PDF for: {p['title']}...")
                                        full_text = download_and_extract_pdf(pdf_url)
                                        if full_text:
                                            p["full_text"] = full_text
                                            p["oa_pdf_url"] = pdf_url
                    except Exception as e:
                        logger.warning(f"Unpaywall OA check failed for DOI {doi}: {e}")

        if feedback_callback:
            feedback_callback("Scoring papers along three dimensions (Methodology, Results, Novelty)...")
            
        # Score each paper
        scores = []
        for p in papers:
            score = self.paper_scorer.score(p)
            scores.append(score)

        if feedback_callback:
            feedback_callback("Detecting contradictions and mapping claims...")
            
        # Detect contradictions
        contradictions = self.contradiction_detector.detect(papers)

        if feedback_callback:
            feedback_callback("Synthesizing literature review summary and key themes...")
            
        # Synthesize summary and themes
        combined = "\n\n".join([f"Title: {p['title']}\nAbstract: {p['summary'][:400]}" for p in papers[:6]])
        summary_prompt = f"""You are an academic literature reviewer. Given the following academic research papers for the query '{query}', write:
1. A 2-3 paragraph executive literature review summary.
2. A list of 3-5 key themes identified (as bullet points).

Papers:
{combined}

Output format:
Summary:
[Your executive summary paragraphs here]

Key Themes:
- Theme 1
- Theme 2
"""
        try:
            summary = self.model_provider.generate(summary_prompt, temperature=0.5)
            summary_text = ""
            themes = []
            
            parts = summary.split("Key Themes:")
            summary_text = parts[0].replace("Summary:", "").strip()
            if len(parts) > 1:
                for line in parts[1].split("\n"):
                    line_strip = line.strip()
                    if line_strip.startswith("-") or line_strip.startswith("*"):
                        themes.append(line_strip.lstrip("-* ").strip())
        except Exception as e:
            logger.error(f"Failed to generate academic summary: {e}")
            summary_text = "Failed to generate summary."
            themes = []

        if feedback_callback:
            feedback_callback("Performing systematic research gap analysis...")

        # Find research gaps based on the summary
        gap_prompt = f"""You are an expert research planner. Based on the following literature review summary on '{query}', perform a systematic research gap analysis.
        
Identify:
1. WHAT IS ESTABLISHED: Consensus or well-proven concepts across the papers.
2. WHAT IS CONTESTED: Disagreements, conflicting findings, or inconsistencies between the studies.
3. WHAT IS UNEXPLORED: Empty spaces, future work directions, or missing variables that have not been investigated.

Summary:
{summary_text}

Output format:
Established Consensus:
- [Consensus item 1]
- [Consensus item 2]

Contested/Conflicting Areas:
- [Conflict item 1]
- [Conflict item 2]

Unexplored Research Gaps:
- [Gap item 1]
- [Gap item 2]
"""
        established = []
        contested = []
        gaps = []
        try:
            gap_response = self.model_provider.generate(gap_prompt, temperature=0.5)
            current_section = None
            for line in gap_response.split("\n"):
                line_strip = line.strip()
                if not line_strip:
                    continue
                if "Established Consensus:" in line_strip:
                    current_section = "established"
                    continue
                elif "Contested/Conflicting Areas:" in line_strip:
                    current_section = "contested"
                    continue
                elif "Unexplored Research Gaps:" in line_strip:
                    current_section = "gaps"
                    continue
                
                if line_strip.startswith("-") or line_strip.startswith("*") or re.match(r"^\d+\.", line_strip):
                    cleaned = re.sub(r"^[-*\d\.\s]+", "", line_strip).strip()
                    if cleaned:
                        if current_section == "established":
                            established.append(cleaned)
                        elif current_section == "contested":
                            contested.append(cleaned)
                        elif current_section == "gaps":
                            gaps.append(cleaned)
        except Exception as e:
            logger.error(f"Failed to generate gaps: {e}")

        # Compute average methodology score as overall confidence
        avg_methodology = sum(s.get("methodology", 50) for s in scores) / len(scores) if scores else 0.0

        report_data = {
            "query": query,
            "papers": papers,
            "scores": scores,
            "contradictions": contradictions,
            "gaps": gaps or ["Insufficient data to determine research gaps."],
            "established": established or ["No clear consensus documented."],
            "contested": contested or ["No explicit contradictions/conflicts highlighted."],
            "summary": summary_text,
            "themes": themes,
            "confidence": avg_methodology
        }

        if feedback_callback:
            feedback_callback("Generating reports and exporting citation formats...")

        # Generate reports
        markdown_report = self.academic_reporter.generate_markdown(report_data)
        latex_report = self.academic_reporter.generate_latex(report_data)
        report_data["markdown"] = markdown_report
        report_data["latex"] = latex_report

        # Save files to reports_dir
        reports_dir = self.config.get("output", {}).get("reports_dir", "./reports")
        os.makedirs(reports_dir, exist_ok=True)
        safe_query = re.sub(r'[^a-zA-Z0-9_\-]', '_', query)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save markdown
        report_path = os.path.join(reports_dir, f"report_academic_{safe_query}_{timestamp}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        report_data["report_path"] = report_path
        
        # Save LaTeX
        latex_path = os.path.join(reports_dir, f"report_academic_{safe_query}_{timestamp}.tex")
        with open(latex_path, "w", encoding="utf-8") as f:
            f.write(latex_report)
        report_data["latex_path"] = latex_path
        
        # Export BibTeX
        bib_path = os.path.join(reports_dir, f"references_{safe_query}_{timestamp}.bib")
        export_bibtex(papers, bib_path)
        report_data["bib_path"] = bib_path
        
        # Export RIS
        from api.export_ris import export_ris
        ris_path = os.path.join(reports_dir, f"references_{safe_query}_{timestamp}.ris")
        export_ris(papers, ris_path)
        report_data["ris_path"] = ris_path
        
        # Export CSV
        from api.export_csv import export_csv
        csv_path = os.path.join(reports_dir, f"references_{safe_query}_{timestamp}.csv")
        export_csv(papers, scores, csv_path)
        report_data["csv_path"] = csv_path
        
        # Export Obsidian Notebook
        from api.export_obsidian import export_obsidian
        obsidian_dir = os.path.join(reports_dir, f"obsidian_{safe_query}_{timestamp}")
        export_obsidian(papers, scores, report_data, obsidian_dir)
        report_data["obsidian_dir"] = obsidian_dir

        if feedback_callback:
            feedback_callback("Packaging workspace bundle...")

        # Export Zip bundle
        from api.export_packager import package_review
        zip_path = os.path.join(reports_dir, f"review_{safe_query}_{timestamp}.zip")
        package_review(
            report_path=report_path,
            latex_path=latex_path,
            bib_path=bib_path,
            ris_path=ris_path,
            csv_path=csv_path,
            obsidian_dir=obsidian_dir,
            zip_path=zip_path
        )
        report_data["zip_path"] = zip_path
        
        # Save to memory if enabled
        if self.memory:
            from memory.types import KnowledgeMemory
            mem_content = f"Academic Literature Review on '{query}' compiled with {len(papers)} papers. Avg methodology confidence: {avg_methodology:.1f}%."
            self.memory.add(KnowledgeMemory(
                id=f"academic_{timestamp}",
                topic=query,
                content=mem_content,
                timestamp=datetime.now(),
                confidence=avg_methodology,
                metadata={"report_path": report_path, "bib_path": bib_path, "zip_path": zip_path}
            ))

        self.final_report = report_data
        return report_data

    async def run_async(
        self,
        query: str,
        languages: List[str] = None,
        mode: str = "balanced",
        max_loops: Optional[int] = None,
        regions: List[str] = None,
        memory_mode: str = "ask",
        feedback_callback = None,
        academic: bool = False,
        uploaded_papers: List[Dict] = None,
        filter_config: Optional[Dict] = None
    ) -> Dict:
        """Asynchronous entry point supporting progress callbacks and cancellation."""
        self.progress_tracker = ProgressTracker()
        if feedback_callback:
            self.progress_tracker.add_callback(feedback_callback)
        self._cancelled = False
        
        try:
            with anyio.CancelScope() as scope:
                self._cancel_scope = scope
                await self.progress_tracker.update("initializing", "Starting research loop...", 0.0)
                
                if academic:
                    result = await self._run_academic_async(query, mode, max_loops, uploaded_papers, filter_config)
                else:
                    result = await self._run_regular_async(
                        query=query,
                        languages=languages,
                        mode=mode,
                        max_loops=max_loops,
                        regions=regions,
                        memory_mode=memory_mode
                    )
                
                if self.is_cancelled():
                    return {"status": "cancelled", "message": "Research cancelled by user."}
                
                await self.progress_tracker.update("completed", "Research completed successfully!", 1.0)
                self.progress_tracker.complete()
                return result
        except anyio.get_cancelled_exc_class():
            await self.progress_tracker.update("cancelled", "Research was cancelled.", 1.0)
            return {"status": "cancelled", "message": "Research cancelled by user."}
        finally:
            self._cancel_scope = None
            self.progress_tracker = None

    def cancel(self) -> None:
        """Cancel the currently running research task."""
        self._cancelled = True
        if self._cancel_scope:
            self._cancel_scope.cancel()
        if self.progress_tracker:
            self.progress_tracker.cancel()
        logger.info("ResearchAgent cancel requested.")

    def is_cancelled(self) -> bool:
        """Check if the task has been cancelled."""
        return self._cancelled

    async def _run_regular_async(
        self,
        query: str,
        languages: List[str] = None,
        mode: str = "balanced",
        max_loops: Optional[int] = None,
        regions: List[str] = None,
        memory_mode: str = "ask",
    ) -> Dict:
        """Run standard research loop in a separate worker thread."""
        def run_sync_wrapper():
            return self.run(
                query=query,
                languages=languages,
                mode=mode,
                max_loops=max_loops,
                regions=regions,
                memory_mode=memory_mode,
                feedback_callback=None,
                academic=False
            )
        return await asyncio.to_thread(run_sync_wrapper)

    async def _run_academic_async(
        self,
        query: str,
        mode: str,
        max_loops: Optional[int] = None,
        uploaded_papers: List[Dict] = None,
        filter_config: Optional[Dict] = None
    ) -> Dict:
        """Run async academic literature review loop with step updates and cancellation boundaries."""
        logger.info(f"Starting academic literature review (async) for: {query}")
        tracker = self.progress_tracker or ProgressTracker()
        partial_failure = False
        
        await tracker.update("searching", "Searching academic databases (ArXiv, PubMed, OpenAlex)...", 0.1)
        
        loop_limit = max_loops or self.config.get("research", {}).get("loop_limits", {}).get(mode, 5)
        
        if self.is_cancelled():
            return {"status": "cancelled"}
            
        papers = await self.academic_searcher.search_all_async(query, max_results=loop_limit * 5)
        
        if self.is_cancelled():
            return {"status": "cancelled"}
            
        if uploaded_papers:
            papers = uploaded_papers + papers
            
        if filter_config:
            logger.info(f"Applying inclusion/exclusion filters: {filter_config}")
            papers = self._apply_filters(papers, filter_config)
            
        if not papers:
            logger.warning("No academic papers found.")
            await tracker.update("error", "No academic papers found matching filter criteria.", 1.0)
            return {"error": "No academic papers found matching filter criteria."}

        # Unpaywall PDF full text extraction (if enabled)
        fetch_full_text = self.config.get("academic", {}).get("fetch_full_text", True)
        if fetch_full_text:
            await tracker.update("extracting", f"Found {len(papers)} papers. Checking for Open-Access PDFs...", 0.2)
            from core.scraper import download_and_extract_pdf, get_safe_session, is_safe_url
            session = get_safe_session()
            for idx, p in enumerate(papers):
                if self.is_cancelled():
                    return {"status": "cancelled"}
                progress_val = 0.2 + (0.1 * (idx + 1) / len(papers))
                await tracker.update("extracting", f"Checking OA PDF for: {p['title'][:40]}...", progress_val)
                
                if p.get("full_text"):
                    continue
                    
                doi = p.get("doi")
                if doi:
                    try:
                        email = os.getenv("USER_EMAIL") or self.config.get("user_email", "default@example.com")
                        unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
                        if is_safe_url(unpaywall_url):
                            resp = await asyncio.to_thread(session.get, unpaywall_url, timeout=10)
                            if resp.status_code == 200:
                                data = resp.json()
                                if data.get("is_oa") and data.get("best_oa_location"):
                                    pdf_url = data["best_oa_location"].get("url_for_pdf")
                                    if pdf_url:
                                        logger.info(f"Downloading Open-Access PDF (Unpaywall) for: {p['title']}...")
                                        try:
                                            full_text = await asyncio.wait_for(
                                                asyncio.to_thread(download_and_extract_pdf, pdf_url),
                                                timeout=30.0
                                            )
                                            if full_text:
                                                p["full_text"] = full_text
                                                p["oa_pdf_url"] = pdf_url
                                        except asyncio.TimeoutError:
                                            logger.warning(f"Timeout downloading Unpaywall PDF for {doi}")
                                        except Exception as e:
                                            logger.warning(f"Error downloading Unpaywall PDF for {doi}: {e}")
                        
                        # Fallback to CORE API
                        if not p.get("full_text"):
                            from core.key_manager import KeyManager
                            core_key = KeyManager.get_key("core")
                            if core_key:
                                core_url = f"https://api.core.ac.uk/v3/works/doi/{doi}"
                                if is_safe_url(core_url):
                                    headers = {"Authorization": f"Bearer {core_key}"}
                                    core_resp = await asyncio.to_thread(session.get, core_url, headers=headers, timeout=10)
                                    if core_resp.status_code == 200:
                                        core_data = core_resp.json()
                                        download_url = core_data.get("downloadUrl")
                                        if download_url and is_safe_url(download_url):
                                            logger.info(f"Downloading Open-Access PDF (CORE) for: {p['title']}...")
                                            try:
                                                full_text = await asyncio.wait_for(
                                                    asyncio.to_thread(download_and_extract_pdf, download_url),
                                                    timeout=30.0
                                                )
                                                if full_text:
                                                    p["full_text"] = full_text
                                                    p["oa_pdf_url"] = download_url
                                            except asyncio.TimeoutError:
                                                logger.warning(f"Timeout downloading CORE PDF for {doi}")
                                            except Exception as e:
                                                logger.warning(f"Error downloading CORE PDF for {doi}: {e}")
                                            
                            else:
                                logger.info("CORE API Key missing. Skipping CORE PDF download fallback.")
                    except Exception as e:
                        logger.warning(f"Full-text extraction check failed for DOI {doi}: {e}")

        if self.is_cancelled():
            return {"status": "cancelled"}

        await tracker.update("scoring", "Scoring papers along three dimensions...", 0.4)
        
        score_semaphore = asyncio.Semaphore(3)
        
        async def score_single(paper: Dict, idx: int) -> Dict:
            async with score_semaphore:
                if self.is_cancelled():
                    return {
                        "methodology": 50, "results": 50, "novelty": 50,
                        "methodology_sd": 0.0, "results_sd": 0.0, "novelty_sd": 0.0,
                        "justification": "Research cancelled."
                    }
                progress_val = 0.4 + (0.2 * (idx + 1) / len(papers))
                await tracker.update("scoring", f"Scoring paper: {paper['title'][:40]}...", progress_val)
                try:
                    return await asyncio.to_thread(self.paper_scorer.score, paper)
                except Exception as e:
                    logger.error(f"Scoring error for paper {paper.get('title')}: {e}")
                    return {
                        "methodology": 50, "results": 50, "novelty": 50,
                        "methodology_sd": 0.0, "results_sd": 0.0, "novelty_sd": 0.0,
                        "justification": f"Scoring failed: {e}"
                    }
        
        tasks = [score_single(p, i) for i, p in enumerate(papers)]
        scores = list(await asyncio.gather(*tasks))

        if self.is_cancelled():
            return {"status": "cancelled"}

        await tracker.update("citation", "Analyzing citation network...", 0.55)
        citation_net = CitationNetwork()
        await citation_net.build_graph(papers)
        citation_contradictions = citation_net.get_contradictions()
        network_stats = citation_net.get_citation_network_stats()

        if hasattr(self, 'contradiction_detector'):
            try:
                self.contradiction_detector.integrate_citation_network(citation_net)
            except Exception as e:
                logger.error(f"Citation network integration error: {e}")

        if self.is_cancelled():
            return {"status": "cancelled"}

        await tracker.update("analyzing", "Detecting contradictions and mapping claims...", 0.6)
        contradictions = await asyncio.to_thread(self.contradiction_detector.detect, papers)

        if self.is_cancelled():
            return {"status": "cancelled"}

        await tracker.update("synthesizing", "Synthesizing literature review summary...", 0.7)
        combined = "\n\n".join([f"Title: {p['title']}\nAbstract: {p['summary'][:400]}" for p in papers[:6]])
        summary_prompt = f"""You are an academic literature reviewer. Given the following academic research papers for the query '{query}', write:
1. A 2-3 paragraph executive literature review summary.
2. A list of 3-5 key themes identified (as bullet points).

Papers:
{combined}

Output format:
Summary:
[Your executive summary paragraphs here]

Key Themes:
- Theme 1
- Theme 2
"""
        try:
            summary = await asyncio.to_thread(self.model_provider.generate, summary_prompt, temperature=0.5)
            summary_text = ""
            themes = []
            
            parts = summary.split("Key Themes:")
            summary_text = parts[0].replace("Summary:", "").strip()
            if len(parts) > 1:
                for line in parts[1].split("\n"):
                    line_strip = line.strip()
                    if line_strip.startswith("-") or line_strip.startswith("*"):
                        themes.append(line_strip.lstrip("-* ").strip())
        except Exception as e:
            logger.error(f"Failed to generate academic summary: {e}")
            summary_text = "Failed to generate summary."
            themes = []
            partial_failure = True

        if self.is_cancelled():
            return {"status": "cancelled"}

        await tracker.update("gaps", "Performing systematic research gap analysis...", 0.8)
        gap_prompt = f"""You are an expert research planner. Based on the following literature review summary on '{query}', perform a systematic research gap analysis.
        
Identify:
1. WHAT IS ESTABLISHED: Consensus or well-proven concepts across the papers.
2. WHAT IS CONTESTED: Disagreements, conflicting findings, or inconsistencies between the studies.
3. WHAT IS UNEXPLORED: Empty spaces, future work directions, or missing variables that have not been investigated.

Summary:
{summary_text}

Output format:
Established Consensus:
- [Consensus item 1]
- [Consensus item 2]

Contested/Conflicting Areas:
- [Conflict item 1]
- [Conflict item 2]

Unexplored Research Gaps:
- [Gap item 1]
- [Gap item 2]
"""
        established = []
        contested = []
        gaps = []
        try:
            gap_response = await asyncio.to_thread(self.model_provider.generate, gap_prompt, temperature=0.5)
            current_section = None
            for line in gap_response.split("\n"):
                line_strip = line.strip()
                if not line_strip:
                    continue
                if "Established Consensus:" in line_strip:
                    current_section = "established"
                    continue
                elif "Contested/Conflicting Areas:" in line_strip:
                    current_section = "contested"
                    continue
                elif "Unexplored Research Gaps:" in line_strip:
                    current_section = "gaps"
                    continue
                
                if line_strip.startswith("-") or line_strip.startswith("*") or re.match(r"^\d+\.", line_strip):
                    cleaned = re.sub(r"^[-*\d\.\s]+", "", line_strip).strip()
                    if cleaned:
                        if current_section == "established":
                            established.append(cleaned)
                        elif current_section == "contested":
                            contested.append(cleaned)
                        elif current_section == "gaps":
                            gaps.append(cleaned)
        except Exception as e:
            logger.error(f"Failed to generate gaps: {e}")
            partial_failure = True

        if self.is_cancelled():
            return {"status": "cancelled"}

        avg_methodology = sum(s.get("methodology", 50) for s in scores) / len(scores) if scores else 0.0

        report_data = {
            "query": query,
            "papers": papers,
            "scores": scores,
            "contradictions": contradictions,
            "gaps": gaps or ["Insufficient data to determine research gaps."],
            "established": established or ["No clear consensus documented."],
            "contested": contested or ["No explicit contradictions/conflicts highlighted."],
            "summary": summary_text,
            "themes": themes,
            "confidence": avg_methodology,
            "network_stats": network_stats if 'network_stats' in locals() else None,
            "citation_graph": citation_net if 'citation_net' in locals() else None,
            "partial": partial_failure
        }

        await tracker.update("exporting", "Generating reports and exporting citation formats...", 0.9)
        markdown_report = self.academic_reporter.generate_markdown(report_data)
        latex_report = self.academic_reporter.generate_latex(report_data)
        report_data["markdown"] = markdown_report
        report_data["latex"] = latex_report

        reports_dir = self.config.get("output", {}).get("reports_dir", "./reports")
        os.makedirs(reports_dir, exist_ok=True)
        safe_query = re.sub(r'[^a-zA-Z0-9_\-]', '_', query)[:50]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        report_path = os.path.join(reports_dir, f"report_academic_{safe_query}_{timestamp}.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        report_data["report_path"] = report_path
        
        latex_path = os.path.join(reports_dir, f"report_academic_{safe_query}_{timestamp}.tex")
        with open(latex_path, "w", encoding="utf-8") as f:
            f.write(latex_report)
        report_data["latex_path"] = latex_path
        
        bib_path = os.path.join(reports_dir, f"references_{safe_query}_{timestamp}.bib")
        await asyncio.to_thread(export_bibtex, papers, bib_path)
        report_data["bib_path"] = bib_path
        
        from api.export_ris import export_ris
        ris_path = os.path.join(reports_dir, f"references_{safe_query}_{timestamp}.ris")
        await asyncio.to_thread(export_ris, papers, ris_path)
        report_data["ris_path"] = ris_path
        
        from api.export_csv import export_csv
        csv_path = os.path.join(reports_dir, f"references_{safe_query}_{timestamp}.csv")
        await asyncio.to_thread(export_csv, papers, scores, csv_path)
        report_data["csv_path"] = csv_path
        
        from api.export_obsidian import export_obsidian
        obsidian_dir = os.path.join(reports_dir, f"obsidian_{safe_query}_{timestamp}")
        await asyncio.to_thread(export_obsidian, papers, scores, report_data, obsidian_dir)
        report_data["obsidian_dir"] = obsidian_dir

        if self.is_cancelled():
            return {"status": "cancelled"}

        await tracker.update("packaging", "Packaging workspace bundle...", 0.95)
        from api.export_packager import package_review
        zip_path = os.path.join(reports_dir, f"review_{safe_query}_{timestamp}.zip")
        await asyncio.to_thread(
            package_review,
            report_path=report_path,
            latex_path=latex_path,
            bib_path=bib_path,
            ris_path=ris_path,
            csv_path=csv_path,
            obsidian_dir=obsidian_dir,
            zip_path=zip_path
        )
        report_data["zip_path"] = zip_path
        
        if self.memory:
            from memory.types import KnowledgeMemory
            mem_content = f"Academic Literature Review on '{query}' compiled with {len(papers)} papers. Avg methodology confidence: {avg_methodology:.1f}%."
            await asyncio.to_thread(
                self.memory.add,
                KnowledgeMemory(
                    id=f"academic_{timestamp}",
                    topic=query,
                    content=mem_content,
                    timestamp=datetime.now(),
                    confidence=avg_methodology,
                    metadata={"report_path": report_path, "bib_path": bib_path, "zip_path": zip_path}
                )
            )

        self.final_report = report_data
        return report_data

    def _apply_filters(self, papers: List[Dict], filter_config: Dict) -> List[Dict]:
        """Apply inclusion/exclusion filters to papers."""
        from core.filters import FilterConfig, PaperFilter
        
        config = FilterConfig(
            min_year=filter_config.get("min_year"),
            max_year=filter_config.get("max_year"),
            min_impact_factor=filter_config.get("min_impact_factor"),
            allowed_study_designs=filter_config.get("allowed_study_designs", []),
            include_keywords=filter_config.get("include_keywords", []),
            exclude_keywords=filter_config.get("exclude_keywords", [])
        )
        filter_engine = PaperFilter(config)
        return filter_engine.apply(papers)
