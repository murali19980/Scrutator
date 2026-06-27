"""
Tests for REST API routes, CORS origins, and rate limiting.
"""

import pytest
from fastapi.testclient import TestClient
from api.routes import app, RateLimiter

def test_health_endpoint():
    """Test health check route."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_rate_limiter():
    """Test rate limiter logic."""
    limiter = RateLimiter(requests_per_minute=2)
    assert limiter.is_allowed("client_1") is True
    assert limiter.is_allowed("client_1") is True
    assert limiter.is_allowed("client_1") is False  # 3rd request blocked
    
    # Other client is unaffected
    assert limiter.is_allowed("client_2") is True
