"""Tests for KeyManager, SSRFSafeAdapter, and new exporters."""

import pytest
import os
import shutil
import zipfile
import socket
import ipaddress
import httpx
import requests
import requests_mock
from unittest.mock import MagicMock, patch

from core.key_manager import KeyManager
from core.scraper import SSRFSafeAdapter, is_ip_safe, get_safe_session
from api.export_ris import to_ris, export_ris
from api.export_csv import export_csv
from api.export_obsidian import export_obsidian
from api.export_packager import package_review

# 1. KeyManager Tests
def test_key_manager_flow():
    # Test setting, getting, and deleting a key
    with patch("core.key_manager.KEYRING_AVAILABLE", True), \
         patch("keyring.set_password") as mock_set, \
         patch("keyring.get_password") as mock_get, \
         patch("keyring.delete_password") as mock_delete:
         
        mock_get.return_value = "mock_key_value"
        
        # Test set
        assert KeyManager.set_key("openrouter", "mock_key_value") is True
        mock_set.assert_called_once_with("scrutator", "OPENROUTER_API_KEY", "mock_key_value")
        
        # Test get
        assert KeyManager.get_key("openrouter") == "mock_key_value"
        mock_get.assert_called_once_with("scrutator", "OPENROUTER_API_KEY")
        
        # Test delete
        assert KeyManager.delete_key("openrouter") is True
        mock_delete.assert_called_once_with("scrutator", "OPENROUTER_API_KEY")

# 2. SSRF IP Safety Checks
def test_is_ip_safe():
    assert is_ip_safe("127.0.0.1") is False
    assert is_ip_safe("10.0.0.1") is False
    assert is_ip_safe("192.168.1.100") is False
    assert is_ip_safe("127.0.53.53") is False
    assert is_ip_safe("169.254.169.254") is False
    assert is_ip_safe("::1") is False
    assert is_ip_safe("fe80::1") is False
    assert is_ip_safe("8.8.8.8") is True
    assert is_ip_safe("93.184.216.34") is True

# 3. SSRFSafeAdapter and DNS Pinning Tests
def test_ssrf_safe_adapter():
    adapter = SSRFSafeAdapter()
    req = requests.PreparedRequest()
    req.url = "https://example.com/path"
    req.headers = {}
    
    with patch("socket.getaddrinfo") as mock_dns, \
         patch("requests.adapters.HTTPAdapter.send") as mock_super_send:
         
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        mock_super_send.return_value = "mock_response"
        
        resp = adapter.send(req)
        assert resp == "mock_response"
        assert req.url == "https://93.184.216.34/path"
        assert req.headers["Host"] == "example.com"
        mock_super_send.assert_called_once()
        args, kwargs = mock_super_send.call_args
        assert kwargs.get("server_hostname") == "example.com"

def test_ssrf_safe_adapter_unsafe_ip():
    adapter = SSRFSafeAdapter()
    req = requests.PreparedRequest()
    req.url = "https://unsafe-example.com/path"
    req.headers = {}
    
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        
        with pytest.raises(requests.exceptions.RequestException) as exc_info:
            adapter.send(req)
        assert "SSRF Block: Unsafe IP" in str(exc_info.value)

# 4. RIS Export Test
def test_ris_export():
    paper = {
        "title": "A New Surface Code",
        "authors": ["John Doe", "Alice Smith"],
        "year": "2026",
        "journal": "Quantum Review",
        "doi": "10.1007/12345",
        "url": "https://example.com/paper",
        "summary": "This is a summary of the paper.",
        "source": "arxiv"
    }
    ris_str = to_ris(paper)
    assert "TY  - JOUR" in ris_str
    assert "TI  - A New Surface Code" in ris_str
    assert "AU  - Doe, John" in ris_str
    assert "AU  - Smith, Alice" in ris_str
    assert "PY  - 2026///" in ris_str
    assert "JO  - Quantum Review" in ris_str
    assert "DO  - 10.1007/12345" in ris_str
    assert "UR  - https://example.com/paper" in ris_str
    assert "N2  - This is a summary of the paper." in ris_str

# 5. CSV Export Test
def test_csv_export(tmp_path):
    papers = [
        {"title": "Paper 1", "authors": ["A1"], "year": "2025", "source": "arxiv"}
    ]
    scores = [
        {"methodology": 80, "results": 85, "novelty": 75}
    ]
    csv_file = tmp_path / "test.csv"
    export_csv(papers, scores, str(csv_file))
    
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8-sig")
    assert "Paper 1" in content
    assert "A1" in content
    assert "80" in content

# 6. Obsidian Export Test
def test_obsidian_export(tmp_path):
    papers = [
        {"title": "Paper 1", "authors": ["A1"], "year": "2025", "source": "arxiv", "summary": "Abstract"}
    ]
    scores = [
        {"methodology": 80, "results": 85, "novelty": 75, "justification": "Details"}
    ]
    report_data = {
        "query": "superconductors",
        "summary": "Executive summary text.",
        "themes": ["Theme A"],
        "confidence": 80.0,
        "contradictions": [],
        "gaps": ["Gap A"]
    }
    
    obsidian_dir = tmp_path / "obsidian"
    export_obsidian(papers, scores, report_data, str(obsidian_dir))
    
    assert obsidian_dir.exists()
    assert (obsidian_dir / "Overview_Index.md").exists()
    assert (obsidian_dir / "Paper 1.md").exists()
    
    index_content = (obsidian_dir / "Overview_Index.md").read_text(encoding="utf-8")
    assert "superconductors" in index_content
    assert "Paper 1" in index_content
    assert "Gap A" in index_content
    
    paper_content = (obsidian_dir / "Paper 1.md").read_text(encoding="utf-8")
    assert "methodology_score: 80" in paper_content

# 7. Zip Packager Test
def test_zip_packager(tmp_path):
    # Create mock files
    md = tmp_path / "report.md"
    md.write_text("MD content")
    tex = tmp_path / "report.tex"
    tex.write_text("Tex content")
    bib = tmp_path / "references.bib"
    bib.write_text("Bib content")
    ris = tmp_path / "references.ris"
    ris.write_text("Ris content")
    csv = tmp_path / "references.csv"
    csv.write_text("CSV content")
    
    obsidian_dir = tmp_path / "obsidian"
    os.makedirs(obsidian_dir, exist_ok=True)
    (obsidian_dir / "note1.md").write_text("note content")
    
    zip_out = tmp_path / "review.zip"
    package_review(str(md), str(tex), str(bib), str(ris), str(csv), str(obsidian_dir), str(zip_out))
    
    assert zip_out.exists()
    with zipfile.ZipFile(zip_out, 'r') as z:
        names = z.namelist()
        assert "report.md" in names
        assert "report.tex" in names
        assert "references.bib" in names
        assert "references.ris" in names
        assert "references.csv" in names
        assert "obsidian/note1.md" in names
