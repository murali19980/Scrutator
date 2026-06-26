"""Scrutator Environment Test Script

Run this script to verify your setup is ready.
"""
import os
import sys
import subprocess
from pathlib import Path

def test_openrouter():
    """Test OpenRouter API connectivity."""
    try:
        import httpx
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key or api_key == "your_openrouter_api_key_here":
            print("❌ OPENROUTER_API_KEY not set in .env")
            return False
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": "Reply with 'OK'"}],
                "max_tokens": 5
            },
            timeout=10
        )
        response.raise_for_status()
        print("✅ OpenRouter API is working!")
        return True
    except Exception as e:
        print(f"❌ OpenRouter test failed: {e}")
        return False

def test_dependencies():
    """Test that all core dependencies are importable."""
    required = ["httpx", "dotenv", "yaml", "bs4", "gradio", "fastapi", "uvicorn", "langdetect", "structlog", "tqdm"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_"))
            print(f"✅ {pkg} installed")
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"❌ Missing: {missing}")
        return False
    print("✅ All core dependencies installed")
    return True

def test_docker():
    """Check if Docker is available (optional)."""
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Docker installed")
            return True
        else:
            print("ℹ️ Docker not found (fallback search will be used)")
            return False
    except FileNotFoundError:
        print("ℹ️ Docker not installed (fallback search will be used)")
        return False

def main():
    print("=" * 50)
    print("🔍 Scrutator Environment Check")
    print("=" * 50)
    test_dependencies()
    test_docker()
    test_openrouter()
    print("\n✅ Environment check complete!")
    print("\nNext steps:")
    print("1. 'pip install -r requirements.txt' - Install dependencies")
    print("2. Set OPENROUTER_API_KEY in .env")
    print("3. 'python -m api.cli \"your query\"' - Run research")
    print("4. 'python -m api.web_ui' - Launch web interface")

if __name__ == "__main__":
    main()
