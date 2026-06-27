"""Tests for scraper module — updated to use respx (httpx mocking) instead of requests_mock."""

import pytest
import httpx
import respx
from core.scraper import (
    is_ip_safe,
    is_safe_url,
    ContentExtractor,
    SSRFSafeTransport,
    SSRFSafeAsyncTransport,
    make_safe_client,
    make_safe_async_client,
)


# ---------------------------------------------------------------------------
# is_ip_safe tests
# ---------------------------------------------------------------------------

class TestIsIpSafe:
    def test_public_ipv4_is_safe(self):
        assert is_ip_safe("8.8.8.8") is True

    def test_loopback_blocked(self):
        assert is_ip_safe("127.0.0.1") is False

    def test_private_10_blocked(self):
        assert is_ip_safe("10.0.0.1") is False

    def test_private_172_blocked(self):
        assert is_ip_safe("172.31.0.1") is False

    def test_private_192_168_blocked(self):
        assert is_ip_safe("192.168.1.1") is False

    def test_link_local_blocked(self):
        assert is_ip_safe("169.254.169.254") is False  # AWS metadata endpoint

    def test_ipv6_loopback_blocked(self):
        assert is_ip_safe("::1") is False

    def test_ipv6_private_blocked(self):
        assert is_ip_safe("fc00::1") is False

    def test_ipv6_link_local_blocked(self):
        assert is_ip_safe("fe80::1") is False

    def test_ipv4_mapped_ipv6_private_blocked(self):
        # ::ffff:10.0.0.1 maps to the private range 10.0.0.1
        assert is_ip_safe("::ffff:10.0.0.1") is False

    def test_invalid_ip_blocked(self):
        assert is_ip_safe("not-an-ip") is False


# ---------------------------------------------------------------------------
# is_safe_url tests
# ---------------------------------------------------------------------------

class TestIsSafeUrl:
    def test_non_http_scheme_blocked(self):
        assert is_safe_url("ftp://example.com/file") is False
        assert is_safe_url("file:///etc/passwd") is False

    def test_empty_url_blocked(self):
        assert is_safe_url("") is False

    def test_no_host_blocked(self):
        assert is_safe_url("https://") is False


# ---------------------------------------------------------------------------
# SSRFSafeTransport tests
# ---------------------------------------------------------------------------

class TestSSRFSafeTransport:
    def test_transport_raises_on_private_ip(self, monkeypatch):
        """SSRF transport should block requests to private IPs."""
        # Monkeypatch is_safe_url to simulate a private resolution
        import core.scraper as scraper_module
        monkeypatch.setattr(scraper_module, "is_safe_url", lambda url: False)
        transport = SSRFSafeTransport()
        with pytest.raises(ValueError, match="SSRF blocked"):
            request = httpx.Request("GET", "http://192.168.1.1/")
            transport.handle_request(request)

    def test_make_safe_client_returns_client(self):
        client = make_safe_client()
        assert isinstance(client, httpx.Client)
        client.close()

    def test_make_safe_async_client_returns_client(self):
        client = make_safe_async_client()
        assert isinstance(client, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# ContentExtractor tests (using respx for httpx mocking)
# ---------------------------------------------------------------------------

class TestContentExtractor:
    HTML = """
    <html>
        <head><title>Test Article Title</title></head>
        <body>
            <header>Header to ignore</header>
            <nav>Navigation to ignore</nav>
            <main>
                <h1>Main Heading</h1>
                <p>This is the first paragraph that contains article content.</p>
                <p>This is the second paragraph which is also content.</p>
            </main>
            <footer>Footer to ignore</footer>
        </body>
    </html>
    """

    @respx.mock
    def test_scraper_fallback_success(self):
        url = "https://example.com/article"
        # Patch is_safe_url so respx can intercept without DNS resolution
        import core.scraper as scraper_module
        original = scraper_module.is_safe_url
        scraper_module.is_safe_url = lambda u: True  # let respx handle it

        respx.get(url).mock(return_value=httpx.Response(200, text=self.HTML))

        extractor = ContentExtractor(fallback=True)
        result = extractor.extract(url)

        scraper_module.is_safe_url = original  # restore

        assert result is not None
        assert result["url"] == url
        assert result["title"] == "Test Article Title"
        assert "first paragraph" in result["text"]
        assert "second paragraph" in result["text"]
        assert "Header to ignore" not in result["text"]
        assert "Navigation to ignore" not in result["text"]

    @respx.mock
    def test_scraper_fallback_failure(self):
        url = "https://example.com/broken"
        import core.scraper as scraper_module
        original = scraper_module.is_safe_url
        scraper_module.is_safe_url = lambda u: True

        respx.get(url).mock(return_value=httpx.Response(404))
        extractor = ContentExtractor(fallback=True)
        result = extractor.extract(url)

        scraper_module.is_safe_url = original
        assert result is None

    def test_unsafe_url_returns_none(self, monkeypatch):
        import core.scraper as scraper_module
        monkeypatch.setattr(scraper_module, "is_safe_url", lambda u: False)
        extractor = ContentExtractor(fallback=True)
        result = extractor.extract("http://192.168.1.100/evil")
        assert result is None
