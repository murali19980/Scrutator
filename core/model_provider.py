"""Unified interface for LLM providers."""

import os
import httpx
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class ModelProvider:
    def __init__(
        self,
        provider: str = "openrouter",
        model: str = "openrouter/free",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 60
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.getenv(f"{provider.upper()}_API_KEY")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response from the LLM."""
        if self.provider == "openrouter":
            return self._openrouter_generate(prompt, system_prompt)
        elif self.provider == "openai":
            return self._openai_generate(prompt, system_prompt)
        elif self.provider == "anthropic":
            return self._anthropic_generate(prompt, system_prompt)
        elif self.provider == "ollama":
            return self._ollama_generate(prompt, system_prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _openrouter_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call OpenRouter API."""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenRouter generation failed: {e}")
            raise

    def _openai_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call OpenAI API."""
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _anthropic_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Anthropic API."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()

    def _ollama_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call local Ollama instance."""
        import requests

        url = "http://localhost:11434/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or "",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        response = requests.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        # Ollama returns a stream; we collect the full response
        full_text = ""
        for line in response.iter_lines():
            if line:
                import json
                data = json.loads(line)
                full_text += data.get("response", "")
                if data.get("done"):
                    break
        return full_text.strip()
