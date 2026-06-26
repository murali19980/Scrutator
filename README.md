# Scrutator Academic

**AI-powered literature reviews, methodology scoring, and BibTeX exports—built for researchers.**

Scrutator Academic is a local-first, AI-powered research assistant focused exclusively on automating academic literature reviews. It queries scholarly databases (ArXiv, PubMed, and OpenAlex), extracts abstracts, detects conflicting claims, grades research methodology, and outputs structured LaTeX, BibTeX, and Markdown reports.

---

## ✨ Features

- **Academic Search**: Searches across ArXiv, PubMed (NCBI E-utilities), and OpenAlex in parallel.
- **SSRF & Input Security**: Integrated URL validation blocks private IP ranges (RFC 1918, link-local, loopback) and sanitizes search terms to prevent injection.
- **Three-Factor Scoring**: Grades retrieved papers along three dimensions (0–100):
  1. *Methodology*: Soundness of research design, controls, and sample size.
  2. *Results*: Reproducibility, statistical claims, and consistency.
  3. *Novelty*: Contribution and originality in the field.
- **Contradiction Detection**: Automatically maps conflicts and differing outcomes between papers.
- **Academic Export Formatting**: Compiles literature review summaries into **LaTeX**, **BibTeX** (`.bib`), and **Markdown** documents.
- **Memory Integration**: Remembers reviewed topics and user preferences (JSON storage with semantic ChromaDB support).
- **Multiple Interfaces**: Command-line interface (CLI) and custom glassmorphic Web UI (Gradio).

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- OpenRouter API key (free tier supported) – sign up at [openrouter.ai](https://openrouter.ai)

### Setup
1. **Clone the repository**
   ```bash
   git clone https://github.com/murali19980/Scrutator.git
   cd Scrutator
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   Create a `.env` file in the root directory:
   ```env
   OPENROUTER_API_KEY=your_api_key_here
   USER_EMAIL=your.email@example.com
   ```

4. **Verify installation**
   ```bash
   python test_environment.py
   ```

---

## 🚀 Usage

### Command Line (CLI)
Run a literature review using the `--academic` flag:
```bash
# Literature review on a topic
python -m api.cli "quantum error correction using surface codes" --academic

# Literature review with quick mode (limit paper iterations)
python -m api.cli "solid-state battery electrolyte interfaces" --academic --mode quick
```
Reports and reference bibliography files will be saved in the `reports/` folder.

### Gradio Web UI
Launch the browser dashboard:
```bash
python -m api.web_ui
```
Open your browser at `http://127.0.0.1:7860`. You can toggle **Academic Mode**, run searches, read summary reviews, and download LaTeX, BibTeX, and Markdown exports directly.

---

## 🧪 Testing

Run unit tests containing mocked API responses:
```bash
pytest tests/ -v
```

---

## 📂 Project Structure

```
Scrutator/
├── core/
│   ├── searcher_academic.py       # ArXiv, PubMed, OpenAlex query client
│   ├── paper_scorer.py            # Methodology, Results, and Novelty scorer
│   ├── contradiction_detector.py  # Conflict mapper
│   ├── reporter_academic.py       # LaTeX & Markdown generator
│   ├── research_agent.py          # Academic pipeline orchestrator
│   ├── scraper.py                 # Scraper with SSRF protection filters
│   └── model_provider.py          # LLM API abstraction
│
├── api/
│   ├── cli.py                     # Click CLI
│   ├── web_ui.py                  # Gradio UI dashboard
│   └── export_bibtex.py           # BibTeX formatting exporter
│
├── config/
│   ├── academic_sources.yaml      # Search endpoints configuration
│   └── settings.yaml              # App configuration settings
│
├── memory/                        # Local memory vault storage
└── tests/                         # pytest test suite
```

---

## 📄 License

MIT License.
