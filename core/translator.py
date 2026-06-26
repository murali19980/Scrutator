"""Translation module using ModelProvider."""

import logging
from typing import Optional
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0  # Make language detection deterministic

from core.model_provider import ModelProvider

logger = logging.getLogger(__name__)

class Translator:
    def __init__(self, model_provider: ModelProvider, target_language: str = "English"):
        self.model_provider = model_provider
        self.target_language = target_language

    def translate(self, text: str, source_lang: Optional[str] = None) -> str:
        """Translate text to target language. Auto-detect source if not provided."""
        if not text or len(text.strip()) == 0:
            return ""

        if not source_lang:
            try:
                source_lang = detect(text)
                logger.debug(f"Detected language: {source_lang}")
            except Exception as e:
                logger.debug(f"Language detection failed: {e}")
                source_lang = "unknown"

        # Treat en or unknown as English (skip translation)
        if source_lang == "en" or source_lang == "unknown":
            return text

        prompt = (
            f"Translate the following {source_lang} text to {self.target_language}. "
            f"Maintain the factual meaning. Only output the translated text, do not add "
            f"any conversational prefixes, introductions, or explanations:\n\n{text}"
        )
        try:
            translated = self.model_provider.generate(prompt)
            return translated
        except Exception as e:
            logger.error(f"Translation failed from {source_lang} to {self.target_language}: {e}")
            return f"[Translation failed] {text}"
