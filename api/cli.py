"""Command-line interface for Scrutator."""

import click
import os
import yaml
import logging
from datetime import datetime
from dotenv import load_dotenv

from core.research_agent import ResearchAgent
from memory.types import FeedbackMemory
from tqdm import tqdm

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("scrutator.cli")

def load_config() -> dict:
    """Load configuration from settings.yaml."""
    from core.config import get_config_path
    config_path = get_config_path("settings.yaml")
    if not os.path.exists(config_path):
        # Fallback empty config structure
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
    
    # Load country_language_map if it exists
    cmap_path = get_config_path("country_language_map.yaml")
    if os.path.exists(cmap_path):
        with open(cmap_path, "r", encoding="utf-8") as f:
            cmap_data = yaml.safe_load(f)
            config["country_language_map"] = cmap_data.get("country_language_map", {})
            
    return config

@click.command()
@click.argument("query", required=False)
@click.option("--regions", "-r", help="Comma-separated country codes (e.g. US,CN,DE)")
@click.option("--languages", "-l", help="Comma-separated language codes (e.g. en,zh,de)")
@click.option("--mode", "-m", default="balanced", type=click.Choice(["quick", "balanced", "deep"]), help="Research mode")
@click.option("--max-loops", "-n", type=int, help="Override maximum research loops")
@click.option("--memory", default="ask", type=click.Choice(["auto", "ask", "off"]), help="Memory application mode")
@click.option("--feedback", is_flag=True, help="Collect user feedback after research finishes")
@click.option("--verbose", is_flag=True, help="Show debug logs")
@click.option("--academic", is_flag=True, help="Run in academic literature review mode")
@click.option("--no-progress", is_flag=True, help="Disable the interactive progress bar")
@click.option("--set-key", nargs=2, metavar="<provider> <key_value>", help="Save an API key securely (e.g. openrouter sk-...)")
@click.option("--delete-key", metavar="<provider>", help="Delete a stored API key")
def cli(query, regions, languages, mode, max_loops, memory, feedback, verbose, academic, no_progress, set_key, delete_key):
    """Scrutator - AI-powered autonomous global research assistant."""
    if set_key:
        provider, key_val = set_key
        from core.key_manager import KeyManager
        if KeyManager.set_key(provider, key_val):
            click.echo(f"🟢 Successfully saved API key for '{provider}' securely.")
        else:
            click.echo(f"❌ Failed to save API key for '{provider}'.")
        return
        
    if delete_key:
        from core.key_manager import KeyManager
        if KeyManager.delete_key(delete_key):
            click.echo(f"🟢 Successfully deleted API key for '{delete_key}'.")
        else:
            click.echo(f"❌ Failed to delete API key for '{delete_key}' (key may not exist).")
        return

    if not query:
        click.echo("❌ Error: Missing argument 'QUERY'. Please provide a research topic, or use key management options (e.g. --set-key).")
        return

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Initializing Scrutator...")
    config = load_config()
    
    # Override logging level from config if not verbose
    if not verbose:
        log_level_str = config.get("logging", {}).get("level", "INFO")
        logging.getLogger().setLevel(getattr(logging, log_level_str, logging.INFO))

    agent = ResearchAgent(config)

    # Setup list of languages
    lang_list = ["en"]
    if languages:
        lang_list = [lang.strip() for lang in languages.split(",")]

    # Setup list of regions
    region_list = []
    if regions:
        region_list = [reg.strip().upper() for reg in regions.split(",")]

    # Run the agent
    click.echo("=" * 60)
    if academic:
        click.echo(f"🚀 Starting academic literature review: '{query}'")
        click.echo(f"🌍 Databases: ArXiv, PubMed, OpenAlex | Mode: {mode}")
    else:
        click.echo(f"🚀 Starting research: '{query}'")
        click.echo(f"🌍 Languages: {lang_list} | Mode: {mode} | Memory: {memory}")
    click.echo("=" * 60)

    pbar = None
    if no_progress:
        progress_cb = None
    else:
        pbar = tqdm(total=100, desc="Starting research...", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}%")
        def progress_cb(update):
            pbar.n = int(update.progress * 100)
            pbar.set_description(update.message[:40])
            pbar.refresh()

    try:
        import asyncio
        report_data = asyncio.run(agent.run_async(
            query=query,
            languages=lang_list,
            mode=mode,
            max_loops=max_loops,
            regions=region_list,
            memory_mode=memory,
            feedback_callback=progress_cb,
            academic=academic
        ))
        if pbar:
            pbar.close()
        
        print("\n" + "=" * 60)
        print("🏆 Research Complete!")
        if academic:
            if "error" in report_data:
                print(f"Error: {report_data['error']}")
            else:
                print(f"Methodology Confidence: {report_data['confidence']:.1f}%")
                print(f"Total Papers Found: {len(report_data['papers'])}")
                token_usage = report_data.get("token_usage", {})
                if token_usage:
                    print(f"📊 Tokens Used: {token_usage.get('total_tokens', 0):,} (Input: {token_usage.get('input_tokens', 0):,}, Output: {token_usage.get('output_tokens', 0):,})")
                print(f"Report Saved to: {report_data['report_path']}")
                print(f"BibTeX Saved to: {report_data['bib_path']}")
                print(f"LaTeX Saved to: {report_data['latex_path']}")
        else:
            print(f"Overall Confidence: {report_data['overall_confidence']:.1f}/100")
            print(f"Total Sources Found: {len(report_data['sources'])}")
            print(f"Report Saved to: {report_data['report_path']}")
        print("=" * 60)

        # Collect user feedback if flag is set
        if feedback and agent.memory:
            user_input = input("\n💬 Enter feedback on these findings (e.g., gaps, preferences, corrections): ").strip()
            if user_input:
                fb_id = f"feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                agent.memory.add(FeedbackMemory(
                    id=fb_id,
                    topic=query,
                    content=user_input,
                    timestamp=datetime.now()
                ))
                print("🧠 Feedback saved to memory for future research runs!")

    except KeyboardInterrupt:
        if pbar:
            pbar.close()
        click.echo("\n⏹️ Research cancelled by user.")
        agent.cancel()
        import sys
        sys.exit(0)
    except Exception as e:
        if pbar:
            pbar.close()
        logger.error(f"Research run failed: {e}", exc_info=True)
        print(f"\n❌ Error executing research: {e}")

if __name__ == "__main__":
    cli()
