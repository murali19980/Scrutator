"""Setup script for Scrutator."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="scrutator",
    version="0.1.0",
    author="Scrutator Contributors",
    author_email="you@example.com",
    description="Local-first, AI-powered research assistant for global, multilingual research.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/scrutator",
    packages=find_packages(include=["core", "memory", "api", "config"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.10",
    install_requires=[
        "python-dotenv>=1.0.0",
        "httpx>=0.27.0",
        "requests>=2.32.0",
        "pyyaml>=6.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=5.0.0",
        "gradio>=4.0.0",
        "click>=8.1.0",
        "python-telegram-bot>=20.0",
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
        "chromadb>=0.5.0",
        "sentence-transformers>=2.3.0",
        "langdetect>=1.0.0",
        "structlog>=24.0.0",
        "tqdm>=4.66.0",
    ],
    entry_points={
        "console_scripts": [
            "scrutator=api.cli:cli",
        ],
    },
)
