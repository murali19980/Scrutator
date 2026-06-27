"""
Tests for REST API routes, CORS, rate limiting, and security headers.
"""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from api.routes import app, PersistentRateLimiter


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

def test_health_endpoint():
    """Health check route should return 200 with healthy status."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# Rate limiter unit tests
# ---------------------------------------------------------------------------

def test_rate_limiter_allows_within_limit():
    """Requests within the limit should be allowed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "rate.db")
        limiter = PersistentRateLimiter(db_path=db_path, requests_per_minute=2)
        assert limiter.is_allowed("client_1") is True
        assert limiter.is_allowed("client_1") is True


def test_rate_limiter_blocks_excess_requests():
    """The 3rd request within 1 minute should be blocked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "rate.db")
        limiter = PersistentRateLimiter(db_path=db_path, requests_per_minute=2)
        limiter.is_allowed("client_1")
        limiter.is_allowed("client_1")
        assert limiter.is_allowed("client_1") is False


def test_rate_limiter_independent_clients():
    """Rate limits should be independent per client IP."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "rate.db")
        limiter = PersistentRateLimiter(db_path=db_path, requests_per_minute=1)
        limiter.is_allowed("client_a")
        assert limiter.is_allowed("client_a") is False
        # A different client should still be allowed
        assert limiter.is_allowed("client_b") is True


# ---------------------------------------------------------------------------
# 429 middleware response tests
# ---------------------------------------------------------------------------

def test_rate_limit_middleware_returns_json_response():
    """The middleware should return a proper JSON 429, not a 500 exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "rate.db")
        # Patch the app's rate limiter to a very strict 0-per-minute limit
        import api.routes as routes_module
        original_limiter = routes_module._rate_limiter
        routes_module._rate_limiter = PersistentRateLimiter(
            db_path=db_path, requests_per_minute=0
        )
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")
            assert response.status_code == 429
            body = response.json()
            assert "detail" in body
            assert "Retry-After" in response.headers
        finally:
            routes_module._rate_limiter = original_limiter


def test_rate_limit_response_has_retry_after_header():
    """429 responses must include a Retry-After header."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "rate.db")
        import api.routes as routes_module
        original_limiter = routes_module._rate_limiter
        routes_module._rate_limiter = PersistentRateLimiter(
            db_path=db_path, requests_per_minute=0
        )
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/health")
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert int(response.headers["Retry-After"]) > 0
        finally:
            routes_module._rate_limiter = original_limiter
