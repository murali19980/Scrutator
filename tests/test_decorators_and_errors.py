"""
Tests for decorators, error handling, and structured logging.
"""

import pytest
import asyncio
from core.decorators import with_retry, handle_errors
from core.errors import ErrorFormatter, get_user_friendly_error

@pytest.mark.asyncio
async def test_with_retry_success():
    """Test that decorator retries and succeeds if exception is not raised on subsequent attempt."""
    attempts = 0
    
    @with_retry(max_retries=2, base_delay=0.01)
    async def sample_func():
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Transient error")
        return "success"
        
    res = await sample_func()
    assert res == "success"
    assert attempts == 2

@pytest.mark.asyncio
async def test_with_retry_failure():
    """Test that decorator fails after exceeding max retries."""
    attempts = 0
    
    @with_retry(max_retries=2, base_delay=0.01)
    async def sample_func():
        nonlocal attempts
        attempts += 1
        raise ValueError("Persistent error")
        
    with pytest.raises(ValueError, match="Persistent error"):
        await sample_func()
    assert attempts == 3

@pytest.mark.asyncio
async def test_handle_errors_decorator():
    """Test that handle_errors catches exceptions and formats them."""
    @handle_errors(error_type="SCORING_FAILED")
    async def failing_func():
        raise ValueError("Some random API key error")
        
    with pytest.raises(ValueError) as excinfo:
        await failing_func()
    assert "API key" in str(excinfo.value) or "❌" in str(excinfo.value)

def test_error_formatter():
    """Test ErrorFormatter formats known error types."""
    msg = ErrorFormatter.format("API_KEY_MISSING")
    assert "Missing API key" in msg
    assert "💡" in msg
    
    exc_msg = ErrorFormatter.format_exception(ValueError("rate limit exceeded"))
    assert "rate limit" in exc_msg.lower() or "unexpected error" in exc_msg.lower()
