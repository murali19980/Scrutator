"""Unified interface for LLM providers."""

import os
import httpx
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from core.key_manager import KeyManager

load_dotenv()
logger = logging.getLogger(__name__)

class ModelProvider:
    # Estimate token pricing: tuple of (input_cost_per_1k, output_cost_per_1k)
    PRICING = {
        "openrouter/free": (0.0, 0.0),
        "gpt-4o-mini": (0.00015, 0.0006),
        "claude-3-haiku": (0.00025, 0.00125),
        "gemini-1.5-flash": (0.000075, 0.0003),
        "default": (0.0005, 0.0015)
    }

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
        self.api_key = api_key or KeyManager.get_key(provider)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        
        # Token usage and cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self._last_actual_usage = None

    def get_token_usage(self) -> Dict[str, int]:
        """Return cumulative token usage."""
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens
        }

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response from the LLM and track estimated cost, retrying on transient errors."""
        import time
        max_retries = 3
        backoff = 2.0
        
        for attempt in range(max_retries + 1):
            try:
                self._last_actual_usage = None
                if self.provider == "openrouter":
                    response = self._openrouter_generate(prompt, system_prompt)
                elif self.provider == "openai":
                    response = self._openai_generate(prompt, system_prompt)
                elif self.provider == "anthropic":
                    response = self._anthropic_generate(prompt, system_prompt)
                elif self.provider == "ollama":
                    response = self._ollama_generate(prompt, system_prompt)
                else:
                    raise ValueError(f"Unknown provider: {self.provider}")
                
                self._track_usage(prompt, system_prompt or "", response, self._last_actual_usage)
                return response
            except Exception as e:
                e_str = str(e).lower()
                is_transient = "rate" in e_str or "429" in e_str or "timeout" in e_str or "connection" in e_str or "50" in e_str or "overloaded" in e_str
                if is_transient and attempt < max_retries:
                    sleep_time = backoff ** attempt
                    logger.warning(f"LLM call failed with transient error: {e}. Retrying in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue
                logger.error(f"LLM generation failed after all attempts: {e}")
                raise

    def _track_usage(self, prompt: str, system_prompt: str, response: str, actual_usage: Optional[Dict[str, int]] = None):
        """Track input/output tokens and estimate costs."""
        if actual_usage:
            in_tokens = actual_usage.get("prompt_tokens") or actual_usage.get("input_tokens") or 0
            out_tokens = actual_usage.get("completion_tokens") or actual_usage.get("output_tokens") or 0
        else:
            # Standard heuristic: 1 token ≈ 4 characters in English
            input_len = len(prompt) + len(system_prompt)
            output_len = len(response)
            in_tokens = int(input_len / 4)
            out_tokens = int(output_len / 4)
        
        self.total_input_tokens += in_tokens
        self.total_output_tokens += out_tokens
        
        # Determine pricing model
        pricing_key = "default"
        for key in self.PRICING:
            if key in self.model:
                pricing_key = key
                break
                
        in_rate, out_rate = self.PRICING.get(pricing_key, self.PRICING["default"])
        cost = (in_tokens / 1000.0 * in_rate) + (out_tokens / 1000.0 * out_rate)
        self.total_cost += cost
        logger.debug(f"LLM Call: {in_tokens} input, {out_tokens} output. Estimated Cost: ${cost:.6f}")

    def get_cost_summary(self) -> Dict[str, Any]:
        """Return a dictionary summarizing current run metrics."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost": self.total_cost
        }

    def reset_cost(self):
        """Reset cost tracking metrics."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self._last_actual_usage = None


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
            usage = data.get("usage")
            if usage:
                self._last_actual_usage = {
                    "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens") or 0,
                    "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens") or 0
                }
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
        if hasattr(response, "usage") and response.usage:
            self._last_actual_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
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
        if hasattr(response, "usage") and response.usage:
            self._last_actual_usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens
            }
        return response.content[0].text.strip()

    def _ollama_generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call local Ollama instance using httpx streaming."""
        import json as _json

        url = "http://localhost:11434/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or "",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        ollama_timeout = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)
        full_text = ""
        actual_usage = None
        with httpx.Client(timeout=ollama_timeout, follow_redirects=False) as client:
            with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        data = _json.loads(line)
                        full_text += data.get("response", "")
                        if data.get("done"):
                            prompt_eval_count = data.get("prompt_eval_count", 0)
                            eval_count = data.get("eval_count", 0)
                            if prompt_eval_count or eval_count:
                                actual_usage = {
                                    "prompt_tokens": prompt_eval_count,
                                    "completion_tokens": eval_count,
                                }
                            break
        self._last_actual_usage = actual_usage
        return full_text.strip()

