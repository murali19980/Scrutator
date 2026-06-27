"""Gradio Web UI for Scrutator with glassmorphic dark theme."""

import gradio as gr
import os
import yaml
import logging
import asyncio
from datetime import datetime

from core.research_agent import ResearchAgent
from memory.types import PreferenceMemory, MemoryEntry

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scrutator.web_ui")

# Custom CSS for modern glassmorphism dark theme
custom_css = """
/* Glassmorphism dark theme */
.gradio-container {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e) !important;
    min-height: 100vh;
    padding: 20px;
    font-family: 'Segoe UI', system-ui, sans-serif;
}
.gr-box, .glass-panel {
    background: rgba(255, 255, 255, 0.05) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 16px !important;
    padding: 24px !important;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
    transition: transform 0.2s ease, box-shadow 0.3s ease;
}
.gr-box:hover, .glass-panel:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.6);
}
.gr-button, .accent-btn {
    background: linear-gradient(135deg, #667eea, #764ba2) !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 12px 28px !important;
    font-weight: 600 !important;
    color: white !important;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
}
.gr-button:hover, .accent-btn:hover {
    transform: scale(1.03);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}
.gr-button:active, .accent-btn:active {
    transform: scale(0.97);
}
.gr-textbox input, .gr-textbox textarea {
    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 10px !important;
    color: white !important;
    padding: 12px !important;
}
.gr-textbox input:focus, .gr-textbox textarea:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.3) !important;
}
label, .gr-markdown p, .gr-markdown h1, .gr-markdown h2, .gr-markdown h3 {
    color: #e0e0e0 !important;
}
.gr-markdown h1 {
    font-size: 2.5rem !important;
    font-weight: 700 !important;
    background: linear-gradient(135deg, #667eea, #764ba2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.gr-progress-bar {
    background: linear-gradient(90deg, #667eea, #764ba2) !important;
    border-radius: 8px !important;
}
.gr-checkbox input[type="checkbox"] {
    accent-color: #764ba2;
}
::-webkit-scrollbar {
    width: 8px;
}
::-webkit-scrollbar-track {
    background: rgba(255,255,255,0.05);
    border-radius: 8px;
}
::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #667eea, #764ba2);
    border-radius: 8px;
}
::-webkit-scrollbar-thumb:hover {
    background: #764ba2;
}

/* Header styled with gradient */
.header-title {
    background: linear-gradient(90deg, #818cf8 0%, #c084fc 50%, #38bdf8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 3.5rem !important;
    font-weight: 800 !important;
    text-align: center;
    margin-bottom: 8px !important;
}

.header-subtitle {
    color: #9ca3af !important;
    font-size: 1.1rem !important;
    text-align: center;
    margin-bottom: 30px !important;
}
"""

def load_config() -> dict:
    from core.config import get_config_path
    config_path = get_config_path("settings.yaml")
    if not os.path.exists(config_path):
        return {
            "model": {"provider": "openrouter", "model": "openrouter/free", "temperature": 0.7},
            "search": {"searxng_url": "http://localhost:8888", "fallback_to_public": True},
            "research": {"loop_limits": {"quick": 3, "balanced": 7, "deep": 15}, "confidence_threshold": 85, "min_sources": 10},
            "memory": {"enabled": True, "storage_type": "json", "storage_path": "./memory_store.json"},
            "output": {"reports_dir": "./reports"},
            "translation": {"enabled": True}
        }
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Load country_language_map
    cmap_path = get_config_path("country_language_map.yaml")
    if os.path.exists(cmap_path):
        with open(cmap_path, "r", encoding="utf-8") as f:
            cmap_data = yaml.safe_load(f)
            config["country_language_map"] = cmap_data.get("country_language_map", {})
    return config

# Load settings
config = load_config()
agent = ResearchAgent(config)

async def run_research_ui(
    query, mode, languages, regions, memory_mode, academic_mode, uploaded_pdfs=None,
    min_year=None, max_year=None, min_impact=None, study_designs=None, include_kws="", exclude_kws="",
    progress=gr.Progress()
):
    """Run research and return results to UI."""
    if not query:
        return "Please enter a search query.", None, None, None, None, None, None, "Error: Empty query"
    
    lang_list = [l.strip() for l in languages.split(",") if l.strip()]
    if not lang_list:
        lang_list = ["en"]
        
    region_list = [r.strip() for r in regions.split(",") if r.strip()]
    
    logger.info(f"UI trigger research: {query} (Academic: {academic_mode})")
    
    # Progress callback mapping ProgressUpdate to Gradio progress bar
    def progress_callback(update):
        logger.info(f"[{update.step}] {update.message}")
        progress(update.progress, desc=update.message[:50])
            
    try:
        progress(0.02, desc="Initializing research loop...")
        
        # Handle uploaded local PDFs
        uploaded_papers = []
        if academic_mode and uploaded_pdfs:
            from core.scraper import extract_local_pdf
            for idx, f in enumerate(uploaded_pdfs):
                # Validate file size (max 10MB)
                try:
                    file_size = os.path.getsize(f.name)
                    if file_size > 10 * 1024 * 1024:
                        logger.warning(f"File {f.name} exceeds max size limit of 10MB. Skipping.")
                        continue
                except Exception as e:
                    logger.error(f"Error checking file size for {f.name}: {e}")
                    continue

                # Validate file extension
                if not f.name.lower().endswith(".pdf"):
                    logger.warning(f"File {f.name} is not a PDF file. Skipping.")
                    continue

                # Validate magic bytes header (%PDF)
                try:
                    with open(f.name, "rb") as pdf_file:
                        header = pdf_file.read(4)
                        if header != b"%PDF":
                            logger.warning(f"File {f.name} does not have a valid PDF header. Skipping.")
                            continue
                except Exception as e:
                    logger.error(f"Error checking magic bytes header for {f.name}: {e}")
                    continue

                progress(0.05 + (idx / len(uploaded_pdfs)) * 0.05, desc=f"Reading uploaded PDF: {os.path.basename(f.name)}...")
                pdf_text = extract_local_pdf(f.name)
                if pdf_text:
                    filename = os.path.basename(f.name)
                    title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
                    uploaded_papers.append({
                        "title": title,
                        "summary": pdf_text[:800],
                        "full_text": pdf_text,
                        "authors": ["Local Upload"],
                        "journal": "Local PDF Document",
                        "year": datetime.now().strftime("%Y"),
                        "source": "local_upload",
                        "url": f"file:///{f.name.replace(os.sep, '/')}"
                    })
        
        agent_mem_mode = "auto" if memory_mode == "ask" else memory_mode
        
        filter_config = {}
        if academic_mode:
            if min_year is not None and min_year != "":
                try:
                    filter_config["min_year"] = int(min_year)
                except ValueError:
                    pass
            if max_year is not None and max_year != "":
                try:
                    filter_config["max_year"] = int(max_year)
                except ValueError:
                    pass
            if min_impact is not None and min_impact != "":
                try:
                    filter_config["min_impact_factor"] = float(min_impact)
                except ValueError:
                    pass
            if study_designs:
                filter_config["allowed_study_designs"] = study_designs
            if include_kws and include_kws.strip():
                filter_config["include_keywords"] = [k.strip() for k in include_kws.split(",") if k.strip()]
            if exclude_kws and exclude_kws.strip():
                filter_config["exclude_keywords"] = [k.strip() for k in exclude_kws.split(",") if k.strip()]

        report_data = await agent.run_async(
            query=query,
            languages=lang_list,
            mode=mode,
            regions=region_list,
            memory_mode=agent_mem_mode,
            academic=academic_mode,
            feedback_callback=progress_callback,
            uploaded_papers=uploaded_papers,
            filter_config=filter_config if filter_config else None
        )
        
        if report_data.get("status") == "cancelled":
            return "### ⏹️ Research Cancelled\n\nResearch was cancelled by the user.", None, None, None, None, None, None, "⏹️ Research Cancelled"
            
        if "error" in report_data:
            return f"### ❌ Research Failed\n\n{report_data['error']}", None, None, None, None, None, None, f"Error: {report_data['error']}"
            
        markdown_report = report_data["markdown"]
        report_path = report_data["report_path"]
        
        token_usage = report_data.get("token_usage") or agent.model_provider.get_token_usage()
        token_info = ""
        if token_usage and token_usage.get("total_tokens", 0) > 0:
            token_info = f" | 📊 Tokens: {token_usage.get('total_tokens', 0):,} (Input: {token_usage.get('input_tokens', 0):,}, Output: {token_usage.get('output_tokens', 0):,})"
        
        if academic_mode:
            latex_path = report_data.get("latex_path")
            bib_path = report_data.get("bib_path")
            ris_path = report_data.get("ris_path")
            csv_path = report_data.get("csv_path")
            zip_path = report_data.get("zip_path")
            status_done = f"🟢 Complete! Methodology Confidence: {report_data['confidence']:.1f}%. Saved bundle to {zip_path}{token_info}"
            return markdown_report, report_path, latex_path, bib_path, ris_path, csv_path, zip_path, status_done
        else:
            status_done = f"🟢 Complete! Confidence Score: {report_data['overall_confidence']:.1f}/100. Saved report to {report_path}{token_info}"
            return markdown_report, report_path, None, None, None, None, None, status_done
        
    except Exception as e:
        logger.error(f"UI research failed: {e}", exc_info=True)
        return f"### ❌ Research Failed\n\nError: {e}", None, None, None, None, None, None, f"Error: {e}"

def cancel_research_ui():
    agent.cancel()
    return "⏹️ Cancelling..."

def show_cancel():
    return gr.update(visible=False), gr.update(visible=True)

def hide_cancel():
    return gr.update(visible=True), gr.update(visible=False)

def get_cache_stats() -> str:
    """Get cache statistics."""
    from core.cache import SearchCache
    cache = SearchCache()
    import sqlite3
    try:
        conn = sqlite3.connect(cache.db_path)
        cur = conn.execute("SELECT COUNT(*) FROM search_cache")
        count = cur.fetchone()[0]
        conn.close()
        return f"✅ Cache active (7-day TTL) | Total Cached Queries: {count}"
    except Exception:
        return "✅ Cache active (7-day TTL) | Total Cached Queries: 0"

def list_memories():
    """Retrieve memories formatted for table."""
    if not agent.memory:
        return [["Memory system disabled", "", "", ""]]
    
    entries = agent.memory.entries
    if not entries:
        return [["No memories stored", "", "", ""]]
        
    table_data = []
    for entry in entries:
        table_data.append([
            entry.id,
            entry.type.upper(),
            entry.topic,
            entry.content[:100] + ("..." if len(entry.content) > 100 else ""),
            entry.timestamp.strftime("%Y-%m-%d %H:%M")
        ])
    return table_data

def add_memory_manually(m_type, topic, content):
    """Add a manual memory."""
    if not agent.memory:
        return "Memory system is disabled in settings.", list_memories()
    if not topic or not content:
        return "Topic and content are required.", list_memories()
        
    entry_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if m_type == "Preference":
        entry = PreferenceMemory(id=entry_id, topic=topic, content=content)
    else:
        entry = MemoryEntry(id=entry_id, topic=topic, content=content, type=m_type.lower())
        
    agent.memory.add(entry)
    return f"Successfully added {m_type} memory: {entry_id}", list_memories()

def compress_memories_ui():
    """Compress memories."""
    if not agent.memory:
        return "Memory system is disabled."
    agent.memory.compress()
    return "Memory store compressed successfully."

# Build UI
with gr.Blocks(
    css=custom_css,
    title="Scrutator Academic",
    theme=gr.themes.Soft(
        primary_hue="indigo",
        secondary_hue="purple",
        font=gr.themes.GoogleFont("Segoe UI")
    )
) as demo:
    gr.HTML("<h1 class='header-title'>Scrutator</h1>")
    gr.HTML("<p class='header-subtitle'>Local‑First Multilingual AI Research Assistant</p>")
    
    with gr.Tabs():
        # Research Console Tab
        with gr.Tab("🔍 Research Console"):
            with gr.Row():
                with gr.Column(scale=1, elem_classes="glass-panel"):
                    gr.Markdown("### ⚙️ Research Parameters")
                    query_input = gr.Textbox(label="Research Query", placeholder="Enter your research topic...", lines=2)
                    
                    with gr.Row():
                        mode_input = gr.Dropdown(label="Research Mode", choices=["quick", "balanced", "deep"], value="balanced")
                        memory_input = gr.Dropdown(label="Memory Mode", choices=["auto", "ask", "off"], value="auto")
                    
                    languages_input = gr.Textbox(label="Target Languages (Comma separated)", value="en")
                    regions_input = gr.Textbox(label="Target Regions (Comma separated)", placeholder="US, CN, DE")
                    
                    academic_input = gr.Checkbox(label="Academic Mode (Literature Review)", value=False)
                    uploaded_pdfs_input = gr.File(label="Upload local PDF papers (Optional)", file_count="multiple", file_types=[".pdf"])
                    
                    with gr.Accordion("📚 Academic Filters (Optional)", open=False):
                        min_year_ui = gr.Number(label="Minimum Publication Year", precision=0, value=None)
                        max_year_ui = gr.Number(label="Maximum Publication Year", precision=0, value=None)
                        min_impact_ui = gr.Number(label="Minimum Impact Factor", value=None)
                        study_design_ui = gr.CheckboxGroup(
                            label="Allowed Study Designs",
                            choices=["rct", "review", "meta-analysis", "observational"]
                        )
                        include_keywords_ui = gr.Textbox(label="Include Keywords (comma separated)", placeholder="e.g. quantum, AI")
                        exclude_keywords_ui = gr.Textbox(label="Exclude Keywords (comma separated)", placeholder="e.g. classical")
                    
                    with gr.Row():
                        submit_btn = gr.Button("Start Research Agent", elem_classes="accent-btn")
                        cancel_btn = gr.Button("Cancel Research", elem_classes="sec-btn", visible=False)
                    
                with gr.Column(scale=2, elem_classes="glass-panel"):
                    status_box = gr.Textbox(label="Status / Diagnostics", value="Ready to research", elem_classes="status-log", interactive=False)
                    report_output = gr.Markdown(value="Report will appear here after execution.")
                    with gr.Row():
                        file_output = gr.File(label="Download Markdown Report")
                        latex_output = gr.File(label="Download LaTeX Report")
                        bib_output = gr.File(label="Download BibTeX Citations")
                    with gr.Row():
                        ris_output = gr.File(label="Download RIS References")
                        csv_output = gr.File(label="Download CSV Table")
                        zip_output = gr.File(label="Download Complete Zip Bundle")
 
            submit_btn.click(
                fn=show_cancel,
                inputs=None,
                outputs=[submit_btn, cancel_btn]
            ).then(
                fn=run_research_ui,
                inputs=[
                    query_input, mode_input, languages_input, regions_input, memory_input, academic_input, uploaded_pdfs_input,
                    min_year_ui, max_year_ui, min_impact_ui, study_design_ui, include_keywords_ui, exclude_keywords_ui
                ],
                outputs=[report_output, file_output, latex_output, bib_output, ris_output, csv_output, zip_output, status_box]
            ).then(
                fn=hide_cancel,
                inputs=None,
                outputs=[submit_btn, cancel_btn]
            )
 
            cancel_btn.click(
                fn=cancel_research_ui,
                inputs=[],
                outputs=[status_box]
            )

        # Memory Vault Tab
        with gr.Tab("🧠 Memory Vault"):
            with gr.Row():
                with gr.Column(scale=1, elem_classes="glass-panel"):
                    gr.Markdown("### ➕ Add Preference Memory")
                    mem_type = gr.Dropdown(label="Memory Type", choices=["Preference", "Knowledge", "Feedback"], value="Preference")
                    mem_topic = gr.Textbox(label="Topic", placeholder="e.g. quantum computing, sources preference")
                    mem_content = gr.Textbox(label="Content", placeholder="e.g. User prefers academic publications over news reports.", lines=4)
                    add_mem_btn = gr.Button("Save Memory", elem_classes="accent-btn")
                    mem_status = gr.Label(value="")
                    
                    gr.Markdown("---")
                    compress_btn = gr.Button("Compress Memory Store", elem_classes="sec-btn")
                    compress_status = gr.Label(value="")

                with gr.Column(scale=2, elem_classes="glass-panel"):
                    gr.Markdown("### 🗄️ Active Memory Entries")
                    refresh_btn = gr.Button("Refresh Table", elem_classes="sec-btn")
                    memory_table = gr.Dataframe(
                        headers=["ID", "Type", "Topic", "Preview", "Timestamp"],
                        datatype=["str", "str", "str", "str", "str"],
                        value=list_memories(),
                        interactive=False
                    )

            # Bindings
            add_mem_btn.click(
                fn=add_memory_manually,
                inputs=[mem_type, mem_topic, mem_content],
                outputs=[mem_status, memory_table]
            )
            refresh_btn.click(
                fn=list_memories,
                inputs=[],
                outputs=[memory_table]
            )
            compress_btn.click(
                fn=compress_memories_ui,
                inputs=[],
                outputs=[compress_status]
            )

        # System Diagnostics Tab
        with gr.Tab("⚙️ Settings & Settings"):
            with gr.Column(elem_classes="glass-panel"):
                gr.Markdown("### 🗄️ Cache Settings")
                with gr.Row():
                    cache_status = gr.Textbox(label="Cache Status", value=get_cache_stats(), interactive=False)
                    refresh_cache_btn = gr.Button("Refresh Stats", elem_classes="sec-btn")
                    clear_cache_btn = gr.Button("Clear Search Cache", elem_classes="sec-btn")
                
                gr.Markdown("---")
                gr.Markdown("### 🎛️ Configuration settings")
                settings_yaml = gr.Code(
                    value=yaml.dump(config, default_flow_style=False),
                    language="yaml",
                    label="settings.yaml",
                    interactive=False
                )

            def clear_cache():
                from core.cache import SearchCache
                cache = SearchCache()
                cache.clear_all()
                return get_cache_stats()
                
            def refresh_cache():
                return get_cache_stats()
                
            clear_cache_btn.click(
                fn=clear_cache,
                inputs=[],
                outputs=[cache_status]
            )

            refresh_cache_btn.click(
                fn=refresh_cache,
                inputs=[],
                outputs=[cache_status]
            )

# Auth configuration
UI_USERNAME = os.getenv("SCRUTATOR_WEB_UI_USERNAME") or os.getenv("GRADIO_USERNAME")
UI_PASSWORD = os.getenv("SCRUTATOR_WEB_UI_PASSWORD") or os.getenv("GRADIO_PASSWORD")

auth_creds = None
if UI_USERNAME and UI_PASSWORD:
    auth_creds = (UI_USERNAME, UI_PASSWORD)

if __name__ == "__main__":
    server_name = os.getenv("SCRUTATOR_WEB_UI_BIND") or "127.0.0.1"
    
    if server_name == "0.0.0.0" and not auth_creds:
        import sys
        logger.critical(
            "FATAL: SCRUTATOR_WEB_UI_BIND is set to 0.0.0.0 (public) "
            "but SCRUTATOR_WEB_UI_USERNAME / SCRUTATOR_WEB_UI_PASSWORD are not set.\n"
            "Running a public Gradio endpoint without authentication is a critical "
            "security risk.\n"
            "Set the username and password environment variables before starting, e.g.:\n"
            "  SCRUTATOR_WEB_UI_USERNAME=admin SCRUTATOR_WEB_UI_PASSWORD=strongpassword\n"
            "Refusing to start."
        )
        sys.exit(1)
                    
    demo.launch(
        server_name=server_name,
        server_port=int(os.getenv("SCRUTATOR_WEB_UI_PORT", "7860")),
        auth=auth_creds
    )
