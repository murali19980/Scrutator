"""Generate academic literature review reports (Markdown and LaTeX)."""

from datetime import datetime
from typing import List, Dict
import os
import re

def escape_latex_special_chars(text: str) -> str:
    """Escape standard LaTeX characters to prevent compile crashes."""
    text = text.replace('&', '\\&')
    text = text.replace('%', '\\%')
    text = text.replace('$', '\\$')
    text = text.replace('#', '\\#')
    text = text.replace('_', '\\_')
    text = text.replace('{', '\\{')
    text = text.replace('}', '\\}')
    return text

def markdown_to_latex(md_text: str) -> str:
    """Translate basic Markdown syntax to clean compilable LaTeX."""
    lines = md_text.split("\n")
    latex_lines = []
    
    in_list = False
    in_enum = False
    in_table = False
    
    def process_formatting(text: str) -> str:
        # Bold: **text** -> \textbf{text}
        text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
        # Italic: *text* -> \textit{text}
        text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)
        # Inline code: `code` -> \texttt{code}
        text = re.sub(r'`(.*?)`', r'\\texttt{\1}', text)
        # Hyperlinks: [label](url) -> \href{url}{label}
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\\href{\2}{\1}', text)
        return text

    for line in lines:
        line_strip = line.strip()
        
        # Check closures
        if in_list and not (line_strip.startswith("-") or line_strip.startswith("*")):
            latex_lines.append("\\end{itemize}")
            in_list = False
        if in_enum and not re.match(r"^\d+\.", line_strip):
            latex_lines.append("\\end{enumerate}")
            in_enum = False
        if in_table and not line_strip.startswith("|"):
            latex_lines.append("\\end{tabular}")
            latex_lines.append("\\end{table}")
            in_table = False

        # Header 1
        if line_strip.startswith("# "):
            val = line_strip[2:]
            latex_lines.append(f"\\section{{{process_formatting(val)}}}")
        # Header 2
        elif line_strip.startswith("## "):
            val = line_strip[3:]
            latex_lines.append(f"\\subsection{{{process_formatting(val)}}}")
        # Header 3
        elif line_strip.startswith("### "):
            val = line_strip[4:]
            latex_lines.append(f"\\subsubsection{{{process_formatting(val)}}}")
        # Itemize
        elif line_strip.startswith("- ") or line_strip.startswith("* "):
            if not in_list:
                latex_lines.append("\\begin{itemize}")
                in_list = True
            val = line_strip[2:]
            val_escaped = escape_latex_special_chars(val)
            latex_lines.append(f"  \\item {process_formatting(val_escaped)}")
        # Enumerate
        elif re.match(r"^\d+\.\s+", line_strip):
            if not in_enum:
                latex_lines.append("\\begin{enumerate}")
                in_enum = True
            val = re.sub(r"^\d+\.\s+", "", line_strip)
            val_escaped = escape_latex_special_chars(val)
            latex_lines.append(f"  \\item {process_formatting(val_escaped)}")
        # Quotes
        elif line_strip.startswith("> "):
            val = line_strip[2:]
            val_escaped = escape_latex_special_chars(val)
            latex_lines.append(f"\\begin{{quote}}{process_formatting(val_escaped)}\\end{{quote}}")
        # Line rule
        elif line_strip == "---":
            latex_lines.append("\\hrule")
        # Empty space
        elif not line_strip:
            latex_lines.append("")
        # Tables
        elif line_strip.startswith("|"):
            if "---" in line_strip:
                continue
            cells = [c.strip() for c in line_strip.split("|")[1:-1]]
            cells_escaped = [process_formatting(escape_latex_special_chars(c)) for c in cells]
            
            if not in_table:
                in_table = True
                latex_lines.append("\\begin{table}[h]")
                latex_lines.append("\\centering")
                layout = "|" + "l|" * len(cells)
                latex_lines.append(f"\\begin{{tabular}}{{{layout}}}")
                latex_lines.append("\\hline")
                latex_lines.append(" & ".join(cells_escaped) + " \\\\")
                latex_lines.append("\\hline")
            else:
                latex_lines.append(" & ".join(cells_escaped) + " \\\\")
                latex_lines.append("\\hline")
        # Text line
        else:
            val_escaped = escape_latex_special_chars(line_strip)
            latex_lines.append(process_formatting(val_escaped))

    if in_list:
        latex_lines.append("\\end{itemize}")
    if in_enum:
        latex_lines.append("\\end{enumerate}")
    if in_table:
        latex_lines.append("\\end{tabular}")
        latex_lines.append("\\end{table}")
        
    return "\n".join(latex_lines)

class AcademicReporter:
    def generate_markdown(self, report_data: Dict) -> str:
        query = report_data.get("query", "Untitled")
        papers = report_data.get("papers", [])
        scores = report_data.get("scores", [])
        contradictions = report_data.get("contradictions", [])
        confidence = report_data.get("confidence", 0.0)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        md = f"""# Literature Review: {query}

**Date:** {now}
**Number of Papers:** {len(papers)}
**Overall Methodology Confidence:** {confidence:.1f}%

## Executive Summary
{report_data.get("summary", "No summary available.")}

## Key Themes
{self._format_themes(report_data.get("themes", []))}

## Systematic Research Gap Analysis

### Established Consensus
"""
        established = report_data.get("established", [])
        if established:
            for item in established:
                md += f"- {item}\n"
        else:
            md += "- No established consensus identified.\n"
            
        md += "\n### Contested & Conflicting Areas\n"
        contested = report_data.get("contested", [])
        if contested:
            for item in contested:
                md += f"- {item}\n"
        else:
            md += "- No explicit conflicts highlighted.\n"
            
        md += "\n### Unexplored Gaps & Future Work\n"
        gaps = report_data.get("gaps", [])
        if gaps:
            for item in gaps:
                md += f"- {item}\n"
        else:
            md += "- No clear gaps reported.\n"

        md += "\n## Paper Analysis\n"
        for i, paper in enumerate(papers):
            s = scores[i] if i < len(scores) else {}
            authors = ", ".join(paper.get('authors', [])) if paper.get('authors') else "Anonymous"
            
            # Formulate score string with SD if present
            m_score = f"{s.get('methodology', 0)}"
            if s.get("methodology_sd", 0.0) > 0.0:
                m_score += f" ± {s['methodology_sd']}"
                
            r_score = f"{s.get('results', 0)}"
            if s.get("results_sd", 0.0) > 0.0:
                r_score += f" ± {s['results_sd']}"
                
            n_score = f"{s.get('novelty', 0)}"
            if s.get("novelty_sd", 0.0) > 0.0:
                n_score += f" ± {s['novelty_sd']}"

            md += f"""
### Paper {i+1}: {paper.get('title', 'Untitled')}

- **Authors:** {authors}
- **Journal/Year:** {paper.get('journal', 'N/A')} ({paper.get('year', 'N/A')})
- **DOI:** {paper.get('doi', 'N/A')}
- **Source:** {paper.get('source', 'unknown')}
- **Scores:** Methodology {m_score}, Results {r_score}, Novelty {n_score}
- **Summary:** {paper.get('summary', 'No abstract')[:500]}...
"""

        if contradictions:
            md += "\n## Contradictions & Conflicting Findings\n"
            for c in contradictions:
                md += f"- **Finding A:** {c.get('finding_a')}\n"
                md += f"  **Finding B:** {c.get('finding_b')}\n"
                md += f"  **Conflict:** {c.get('conflict')}\n"
                md += f"  **Confidence:** {c.get('confidence')}\n"

        md += "\n## Methodology\n- Academic databases used: ArXiv, PubMed, OpenAlex\n- Confidence scoring: three-factor (methodology, results, novelty)\n- Contradiction detection via LLM synthesis\n- Rate limiting and SSRF protection applied\n"

        md += "\n## Full Citation List\n"
        for paper in papers:
            authors = ", ".join(paper.get('authors', [])) if paper.get('authors') else "Anonymous"
            title = paper.get('title', 'Untitled')
            md += f"- {authors} ({paper.get('year', 'n.d.')}). *{title}*. {paper.get('journal', '')}\n"

        md += "\n---\n*Report generated by Scrutator Academic.*"
        return md

    def generate_latex(self, report_data: Dict) -> str:
        md = self.generate_markdown(report_data)
        title = report_data.get("query", "Literature Review")
        
        latex_content = markdown_to_latex(md)
        
        latex = f"""\\documentclass{{article}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\usepackage{{booktabs}}
\\geometry{{margin=1in}}
\\title{{{title}}}
\\date{{{datetime.now().strftime("%B %d, %Y")}}}
\\begin{{document}}
\\maketitle

{latex_content}

\\end{{document}}"""
        return latex

    def _format_themes(self, themes: List[str]) -> str:
        if not themes:
            return "No themes identified."
        return "\n".join([f"- {t}" for t in themes])
