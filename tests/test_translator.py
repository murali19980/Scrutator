"""Tests for translator module."""

import pytest
from unittest.mock import MagicMock
from core.translator import Translator
from core.model_provider import ModelProvider

def test_translator_english_direct():
    mock_provider = MagicMock(spec=ModelProvider)
    translator = Translator(model_provider=mock_provider)
    
    # English input should return same text and not call LLM
    text = "This is a clean English sentence."
    result = translator.translate(text)
    
    assert result == text
    mock_provider.generate.assert_not_called()

def test_translator_foreign_calls_llm():
    mock_provider = MagicMock(spec=ModelProvider)
    mock_provider.generate.return_value = "This is the translated text in English."
    translator = Translator(model_provider=mock_provider)
    
    # French input (detected automatically or specified)
    french_text = "Ceci est une phrase en français."
    result = translator.translate(french_text, source_lang="fr")
    
    assert result == "This is the translated text in English."
    mock_provider.generate.assert_called_once()
    assert "Translate" in mock_provider.generate.call_args[0][0]
    assert "fr" in mock_provider.generate.call_args[0][0]
