"""Gradio Web UI for Scrutator with glassmorphic dark theme."""

import gradio as gr
import os
import yaml
import logging
from datetime import datetime

from core.research_agent import ResearchAgent
from memory.types import PreferenceMemory, MemoryEntry

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scrutator.web_ui")

# Custom CSS for modern glassmorphism dark theme
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

body, .gradio-container {
    background: linear-gradient(135deg, #0b0f19 0%, #1a1b35 50%, #0d0f1b 100%) !important;
    font-family: 'Inter', sans-serif !important;
    color: #f3f4f6 !important;
}

h1, h2, h3, h4 {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

/* Glassmorphism card panel */
.glass-panel {
    background: rgba(17, 24, 39, 0.6) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 16px !important;
    padding: 24px !important;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3) !important;
}

/* Gradio container customization */
.gradio-container {
    max-width: 1200px !important;
    margin: 0 auto !important;
}

/* Accent Buttons */
.accent-btn {
    background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 12px !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 14px 0 rgba(99, 102, 241, 0.4) !important;
}

.accent-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px 0 rgba(168, 85, 247, 0.6) !important;
}

/* Secondary Button */
.sec-btn {
    background: rgba(255, 255, 255, 0.05) !important;
    color: #e5e7eb !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 12px !important;
    transition: all 0.2s ease !important;
}

.sec-btn:hover {
    background: rgba(255, 255, 255, 0.1) !important;
    border-color: rgba(255, 255, 255, 0.2) !important;
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

/* Tabs */
.tabs {
    border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
}

.tab-nav button.selected {
    border-bottom-color: #a855f7 !important;
    color: #c084fc !important;
}

/* Custom progress box */
.status-log {
    background-color: #05070f !important;
    border-left: 4px solid #6366f1 !important;
    font-family: 'Courier New', Courier, monospace !important;
    font-size: 0.9rem !important;
    color: #34d399 !important;
    padding: 12px !important;
    border-radius: 8px !important;
}
"""

def load_config() -> dict:
    config_path = "./config/settings.yaml"
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
    cmap_path = "./config/country_language_map.yaml"
    if os.path.exists(cmap_path):
        with open(cmap_path, "r", encoding="utf-8") as f:
            cmap_data = yaml.safe_load(f)
            config["country_language_map"] = cmap_data.get("country_language_map", {})
    return config

# Load settings
config = load_config()
agent = ResearchAgent(config)

def run_research_ui(query, mode, languages, regions, memory_mode, academic_mode, uploaded_pdfs=None, progress=gr.Progress()):
    """Run research and return results to UI."""
    if not query:
        return "Please enter a search query.", None, None, None, None, None, None, "Error: Empty query"
    
    lang_list = [l.strip() for l in languages.split(",") if l.strip()]
    if not lang_list:
        lang_list = ["en"]
        
    region_list = [r.strip() for r in regions.split(",") if r.strip()]
    
    logger.info(f"UI trigger research: {query} (Academic: {academic_mode})")
    
    # Live logger progress status callback
    def progress_callback(status_msg):
        logger.info(status_msg)
        if "Searching" in status_msg:
            progress(0.1, desc=status_msg)
        elif "Checking" in status_msg:
            progress(0.3, desc=status_msg)
        elif "Scoring" in status_msg:
            progress(0.5, desc=status_msg)
        elif "Detecting" in status_msg:
            progress(0.7, desc=status_msg)
        elif "Synthesizing" in status_msg or "gap" in status_msg.lower():
            progress(0.8, desc=status_msg)
        elif "Generating" in status_msg or "Packaging" in status_msg:
            progress(0.9, desc=status_msg)
        else:
            progress(0.95, desc=status_msg)
            
    try:
        progress(0.02, desc="Initializing research loop...")
        
        # Handle uploaded local PDFs
        uploaded_papers = []
        if academic_mode and uploaded_pdfs:
            from core.scraper import extract_local_pdf
            for idx, f in enumerate(uploaded_pdfs):
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
        
        report_data = agent.run(
            query=query,
            languages=lang_list,
            mode=mode,
            regions=region_list,
            memory_mode=agent_mem_mode,
            academic=academic_mode,
            feedback_callback=progress_callback,
            uploaded_papers=uploaded_papers
        )
        
        if "error" in report_data:
            return f"### ❌ Research Failed\n\n{report_data['error']}", None, None, None, None, None, None, f"Error: {report_data['error']}"
            
        markdown_report = report_data["markdown"]
        report_path = report_data["report_path"]
        
        if academic_mode:
            latex_path = report_data.get("latex_path")
            bib_path = report_data.get("bib_path")
            ris_path = report_data.get("ris_path")
            csv_path = report_data.get("csv_path")
            zip_path = report_data.get("zip_path")
            status_done = f"🟢 Complete! Methodology Confidence: {report_data['confidence']:.1f}%. Saved bundle to {zip_path}"
            return markdown_report, report_path, latex_path, bib_path, ris_path, csv_path, zip_path, status_done
        else:
            status_done = f"🟢 Complete! Confidence Score: {report_data['overall_confidence']:.1f}/100. Saved report to {report_path}"
            return markdown_report, report_path, None, None, None, None, None, status_done
        
    except Exception as e:
        logger.error(f"UI research failed: {e}", exc_info=True)
        return f"### ❌ Research Failed\n\nError: {e}", None, None, None, None, None, None, f"Error: {e}"

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
with gr.Blocks(css=custom_css, title="Scrutator Research Assistant") as demo:
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
                    
                    submit_btn = gr.Button("Start Research Agent", elem_classes="accent-btn")
                    
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
                fn=run_research_ui,
                inputs=[query_input, mode_input, languages_input, regions_input, memory_input, academic_input, uploaded_pdfs_input],
                outputs=[report_output, file_output, latex_output, bib_output, ris_output, csv_output, zip_output, status_box]
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
                gr.Markdown("### 🎛️ Configuration settings")
                settings_yaml = gr.Code(
                    value=yaml.dump(config, default_flow_style=False),
                    language="yaml",
                    label="settings.yaml",
                    interactive=False
                )

# Auth configuration
UI_USERNAME = os.getenv("SCRUTATOR_WEB_UI_USERNAME")
UI_PASSWORD = os.getenv("SCRUTATOR_WEB_UI_PASSWORD")

auth_creds = None
if UI_USERNAME and UI_PASSWORD:
    auth_creds = (UI_USERNAME, UI_PASSWORD)

if __name__ == "__main__":
    server_name = os.getenv("SCRUTATOR_WEB_UI_BIND") or "127.0.0.1"
    
    if server_name == "0.0.0.0" and not auth_creds:
        import secrets
        temp_pass = secrets.token_hex(8)
        auth_creds = ("admin", temp_pass)
        logger.info(f"\n=================================================="
                    f"\nRunning Web UI on 0.0.0.0 without custom credentials!"
                    f"\nENFORCING TEMPORARY BASIC AUTH FOR SECURITY:"
                    f"\nUsername: admin"
                    f"\nPassword: {temp_pass}"
                    f"\n==================================================\n")
                    
    demo.launch(
        server_name=server_name,
        server_port=7860,
        auth=auth_creds
    )
