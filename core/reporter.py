"""Markdown report generation for research findings."""

from typing import List, Dict
from datetime import datetime

class Reporter:
    def generate_markdown(
        self,
        query: str,
        findings: Dict,
        confidence_overall: float,
        sources: List[Dict],
        loop_history: List[Dict],
        health_check: Dict,
        followup_questions: List[str]
    ) -> str:
        """
        Generate a structured Markdown report from research results.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Color coding confidence
        if confidence_overall >= 80:
            conf_color = "🟢 HIGH"
        elif confidence_overall >= 50:
            conf_color = "🟡 MEDIUM"
        else:
            conf_color = "🔴 LOW"

        md = []
        md.append(f"# Scrutator Research Report: {query}")
        md.append(f"*Generated on {timestamp}*")
        md.append("")
        md.append("## 📊 Research Summary Metadata")
        md.append("")
        md.append(f"- **Query**: `{query}`")
        md.append(f"- **Overall Confidence Score**: {conf_color} ({confidence_overall:.1f}/100)")
        md.append(f"- **Total Unique Sources Analyzed**: {len(sources)}")
        md.append(f"- **Total Research Loops Executed**: {len(loop_history)}")
        md.append("")
        md.append("---")
        md.append("")
        md.append("## 📰 Executive Summary")
        md.append("")
        md.append(findings.get("summary", "No executive summary available."))
        md.append("")
        md.append("---")
        md.append("")
        md.append("## 💡 Key Insights")
        md.append("")
        for insight in findings.get("key_insights", []):
            md.append(f"- {insight}")
        if not findings.get("key_insights"):
            md.append("- No key insights extracted.")
        md.append("")
        md.append("---")
        md.append("")
        md.append("## 📝 Detailed Synthesis")
        md.append("")
        # We can pass the detailed_synthesis in a separate argument or in findings
        detailed = findings.get("detailed_synthesis", "")
        if not detailed and hasattr(findings, "get"):
            # try detailed_synthesis directly
            detailed = findings.get("detailed_synthesis", "Detailed synthesis not available.")
        md.append(detailed)
        md.append("")
        md.append("---")
        
        # Loop History Table
        md.append("## 🔄 Research Loop Iterations")
        md.append("")
        md.append("| Loop | Query Executed | Sources Found | Confidence Score |")
        md.append("| :--- | :--- | :--- | :--- |")
        for loop in loop_history:
            q_display = loop.get("query", query)
            if len(q_display) > 40:
                q_display = q_display[:37] + "..."
            md.append(f"| {loop['loop']} | `{q_display}` | {loop['sources_found']} | {loop['confidence']:.1f}/100 |")
        md.append("")
        md.append("---")
        
        # Sources List
        md.append("## 📁 Reference Sources")
        md.append("")
        for i, src in enumerate(sources, 1):
            title = src.get("title", "Untitled").strip() or "Untitled Webpage"
            url = src.get("url", "")
            lang = src.get("language", "en")
            snippet = src.get("text", "")[:250].strip().replace('\n', ' ')
            md.append(f"{i}. **[{title}]({url})** (Language: `{lang}`)")
            if snippet:
                md.append(f"   > ... {snippet} ...")
                md.append("")
        if not sources:
            md.append("No reference sources compiled.")
        md.append("")
        md.append("---")

        # Follow-up questions
        md.append("## 🔮 Recommended Follow-up Questions")
        md.append("")
        for i, q in enumerate(followup_questions, 1):
            md.append(f"{i}. {q}")
        if not followup_questions:
            md.append("- No follow-up questions recommended.")
        md.append("")
        md.append("---")
        
        # Health Check
        md.append("## 🛠️ System Health diagnostics")
        md.append("")
        md.append(f"- **Agent Pipeline Status**: `{health_check.get('status', 'Healthy')}`")
        md.append(f"- **Search Backend**: `SearXNG (with public fallbacks)`")
        md.append(f"- **Scraping Engine**: `Crawl4AI + BeautifulSoup parser`")
        
        return "\n".join(md)
