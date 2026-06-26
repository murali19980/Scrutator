"""Telegram bot integration for Scrutator."""

import os
import logging
import yaml
from dotenv import load_dotenv

# Try importing telegram
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

from core.research_agent import ResearchAgent

load_dotenv()
logger = logging.getLogger("scrutator.telegram_bot")

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
        return yaml.safe_load(f)

# Global configuration and agent
config = load_config()
agent = ResearchAgent(config)
current_mode = "balanced"

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message."""
    welcome_text = (
        "🤖 **Welcome to Scrutator Research Assistant Bot!**\n\n"
        "I can perform global, multilingual web research and compile structured reports with confidence scoring.\n\n"
        "**Available Commands:**\n"
        "/research <query> - Start a new research task\n"
        "/mode <quick/balanced/deep> - Change research loop limits\n"
        "/status - View system status\n"
        "/memory - View memory info"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change loop limit mode."""
    global current_mode
    if not context.args:
        await update.message.reply_text(f"Current mode: `{current_mode}`. Set mode using `/mode <quick/balanced/deep>`")
        return
        
    mode = context.args[0].lower()
    if mode in ["quick", "balanced", "deep"]:
        current_mode = mode
        await update.message.reply_text(f"✅ Mode changed to: `{current_mode}`")
    else:
        await update.message.reply_text("❌ Invalid mode. Please choose `quick`, `balanced`, or `deep`.")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check status."""
    status_text = (
        "🤖 **Scrutator Status**\n\n"
        "● Pipeline: `Online`\n"
        f"● Current Loop Mode: `{current_mode}`\n"
        f"● Memory System: `{'Enabled' if config.get('memory', {}).get('enabled') else 'Disabled'}`"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show memory database stats."""
    if not agent.memory:
        await update.message.reply_text("Memory system is disabled in config.")
        return
    count = len(agent.memory.entries)
    await update.message.reply_text(f"🧠 Memory database contains `{count}` stored entries.")

async def research_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perform research query."""
    if not context.args:
        await update.message.reply_text("❌ Please specify a research query. Example: `/research lithium batteries`")
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Starting research on: *{query}*... (This can take 1-3 minutes)", parse_mode="Markdown")

    try:
        # Run research synchronously in this simple bot thread (or run in executor in production)
        # We enforce auto memory retrieval for Telegram Bot
        report_data = agent.run(
            query=query,
            languages=["en"],
            mode=current_mode,
            memory_mode="auto"
        )
        
        # Send summary back
        findings = report_data["findings"]
        confidence = report_data["overall_confidence"]
        
        summary_text = (
            f"🏆 **Research Complete!**\n"
            f"Topic: *{query}*\n"
            f"Overall Confidence: `{confidence:.1f}/100`\n\n"
            f"📰 **Executive Summary:**\n{findings.get('summary', '')[:800]}...\n\n"
            f"📄 Full report saved locally: `{report_data['report_path']}`"
        )
        await update.message.reply_text(summary_text, parse_mode="Markdown")
        
        # Upload report file
        if os.path.exists(report_data["report_path"]):
            with open(report_data["report_path"], "rb") as f:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename=os.path.basename(report_data["report_path"]))
                
    except Exception as e:
        logger.error(f"Telegram research command failed: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Research failed: {e}")

def main():
    """Start telegram bot."""
    if not TELEGRAM_AVAILABLE:
        print("❌ Error: python-telegram-bot is not installed.")
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️ Warning: TELEGRAM_BOT_TOKEN not found in .env. Disabling Telegram bot gracefully.")
        return

    print("🤖 Starting Scrutator Telegram Bot...")
    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("research", research_cmd))

    # Run bot
    app.run_polling()

if __name__ == "__main__":
    main()
