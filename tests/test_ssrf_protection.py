"""Tests for SSRF protection inside core/scraper.py."""

import pytest
import socket
from core.scraper import is_safe_url

@pytest.fixture(autouse=True)
def mock_dns_resolution(monkeypatch):
    """Mock socket.getaddrinfo to avoid network DNS queries during tests."""
    def mock_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        # Unsafe domains/IPs resolve to loopback/private IPs
        if host in ("localhost", "127.0.0.1"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 0))]
        elif host == "192.168.1.1":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 0))]
        elif host == "10.0.0.1":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 0))]
        elif host == "169.254.169.254":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 0))]
        # Safe domains resolve to public IP (8.8.8.8)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0))]
        
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

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
