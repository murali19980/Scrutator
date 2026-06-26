"""Tests for SSRF protection inside core/scraper.py."""

import pytest
from core.scraper import is_safe_url

def test_safe_urls():
    assert is_safe_url("https://www.google.com") is True
    assert is_safe_url("http://arxiv.org/abs/1706.03762") is True
    assert is_safe_url("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/") is True

def test_unsafe_schemas():
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("ftp://ftp.example.com") is False
    assert is_safe_url("gopher://gopher.example.com") is False

def test_unsafe_ips():
    assert is_safe_url("http://127.0.0.1") is False
    assert is_safe_url("https://localhost") is False
    assert is_safe_url("http://192.168.1.1") is False
    assert is_safe_url("http://10.0.0.1") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
